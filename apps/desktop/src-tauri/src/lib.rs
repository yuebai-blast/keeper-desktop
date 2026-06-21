use tauri::Manager;
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

/// sidecar 鉴权 token（prod 启动时随机生成，经 env 给 sidecar、经 IPC 给前端）。dev 为空串=不鉴权。
struct AuthToken(String);

/// sidecar 监听端口（prod 启动时选随机空闲端口，经 --port 给 sidecar、经 IPC 给前端）。dev 固定 8761。
struct SidecarPort(u16);

/// dev 端口：dev 下壳不拉起 sidecar，用 `mise run sidecar` 起在固定 8761，前端与之对齐。
const DEV_PORT: u16 = 8761;

/// 选一个 OS 分配的空闲端口：bind 到 :0 拿到端口号后立刻释放，再交给 sidecar bind。
/// drop 到 sidecar 真正 bind 之间有极小竞态窗口，本机单用户基本不会撞；撞上则 sidecar 启动失败会进 stderr。
fn pick_free_port() -> u16 {
    let listener =
        std::net::TcpListener::bind("127.0.0.1:0").expect("无法绑定空闲端口给 sidecar");
    listener
        .local_addr()
        .expect("无法读取 sidecar 端口")
        .port()
    // listener 在此 drop，端口释放，交给 sidecar
}

/// 生成 32 字节随机 token 的十六进制串。
fn generate_token() -> String {
    let mut buf = [0u8; 32];
    getrandom::getrandom(&mut buf).expect("生成随机 token 失败");
    buf.iter().map(|b| format!("{:02x}", b)).collect()
}

/// 弹出目录选择器，返回用户选中的文件夹绝对路径（取消则 None）。
///
/// 扫描、读 EXIF、复制副本、归档等文件操作都已下沉到 sidecar（Python）；Rust 壳只负责
/// 需要原生 GUI 的能力——目录选择对话框。命令声明为 async，Tauri 会在非主线程上执行，
/// blocking_pick_folder 才不会和主线程 UI 死锁。
#[tauri::command]
async fn pick_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    let Some(picked) = app.dialog().file().blocking_pick_folder() else {
        return Ok(None); // 用户取消
    };
    let dir = picked.into_path().map_err(|e| e.to_string())?;
    Ok(Some(dir.to_string_lossy().into_owned()))
}

/// 用系统默认方式打开一个路径（完成阶段用于打开输出目录）。
#[tauri::command]
fn open_path(app: tauri::AppHandle, path: String) -> Result<(), String> {
    app.opener()
        .open_path(path, None::<&str>)
        .map_err(|e| e.to_string())
}

/// 退出应用——用户在首次下载确认弹窗点「不同意」时调用。
#[tauri::command]
fn exit_app(app: tauri::AppHandle) {
    app.exit(0);
}

/// 前端取 sidecar 鉴权 token（启动时调用一次）。dev 下为空串=前端不发 token。
#[tauri::command]
fn get_auth_token(state: tauri::State<AuthToken>) -> String {
    state.0.clone()
}

/// 前端取 sidecar 监听端口（启动时调用一次，用于拼接基址）。dev 下为 8761。
#[tauri::command]
fn get_sidecar_port(state: tauri::State<SidecarPort>) -> u16 {
    state.0
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        // 在线升级：前端经 @tauri-apps/plugin-updater 查最新版/下载/校验/安装，
        // 装好后经 plugin-process 的 relaunch 重启生效。两者均为桌面端能力。
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            // dev 下不生成 token（前端取到空串=不发；mise run sidecar 也没 KEEPER_AUTH_TOKEN=不鉴权）。
            let token = if cfg!(debug_assertions) {
                String::new()
            } else {
                generate_token()
            };
            app.manage(AuthToken(token.clone()));

            // dev 固定 8761（与 `mise run sidecar` 对齐）；prod 选随机空闲端口避开占用。
            let port = if cfg!(debug_assertions) {
                DEV_PORT
            } else {
                pick_free_port()
            };
            app.manage(SidecarPort(port));

            // 仅打包运行时自动拉起内置 sidecar；dev 下用 `mise run sidecar`，不重复起。
            if !cfg!(debug_assertions) {
                // OS 约定目录：数据根→app_data_dir，模型缓存→app_cache_dir/models（大缓存不进备份）。
                let data_dir = app.path().app_data_dir().expect("无法解析 app_data_dir");
                let models_dir = app
                    .path()
                    .app_cache_dir()
                    .expect("无法解析 app_cache_dir")
                    .join("models");

                let sidecar = app
                    .shell()
                    .sidecar("keeper-sidecar")
                    .expect("缺少 keeper-sidecar 可执行")
                    .args(["--port", &port.to_string()])
                    .env("KEEPER_AUTH_TOKEN", &token)
                    .env("KEEPER_HOME", data_dir)
                    .env("KEEPER_MODELS_DIR", models_dir);
                let (mut rx, _child) = sidecar.spawn().expect("无法启动 keeper-sidecar");
                tauri::async_runtime::spawn(async move {
                    while let Some(event) = rx.recv().await {
                        if let CommandEvent::Stderr(line) | CommandEvent::Stdout(line) = event {
                            eprintln!("[sidecar] {}", String::from_utf8_lossy(&line));
                        }
                    }
                });
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            pick_folder,
            open_path,
            exit_app,
            get_auth_token,
            get_sidecar_port
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
