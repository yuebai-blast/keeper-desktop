use tauri_plugin_dialog::DialogExt;

// 支持的图片/RAW 扩展名（与 sidecar imaging.py 保持一致）
const IMAGE_EXTS: &[&str] = &[
    "jpg", "jpeg", "png", "heic", "heif", "webp", "bmp", "tif", "tiff", "cr2", "cr3", "nef",
    "nrw", "arw", "sr2", "srf", "raf", "rw2", "orf", "dng", "pef", "raw",
];

/// 弹出目录选择器，扫描其中的图片/RAW，返回绝对路径列表。
///
/// 文件系统访问只在 Rust 壳里发生（前端碰不到 FS）。命令声明为 async，
/// Tauri 会在非主线程上执行，blocking_pick_folder 才不会和主线程 UI 死锁。
/// 用户取消选择 → 返回空列表。
#[tauri::command]
async fn import_photos(app: tauri::AppHandle) -> Result<Vec<String>, String> {
    let Some(picked) = app.dialog().file().blocking_pick_folder() else {
        return Ok(vec![]); // 用户取消
    };
    let dir = picked.into_path().map_err(|e| e.to_string())?;

    let mut photos = Vec::new();
    for entry in std::fs::read_dir(&dir).map_err(|e| e.to_string())? {
        let path = entry.map_err(|e| e.to_string())?.path();
        if !path.is_file() {
            continue;
        }
        let is_image = path
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| IMAGE_EXTS.contains(&e.to_lowercase().as_str()))
            .unwrap_or(false);
        if is_image {
            photos.push(path.to_string_lossy().into_owned());
        }
    }
    photos.sort();
    Ok(photos)
}

#[derive(serde::Serialize)]
struct ArchiveSummary {
    winners: usize,
    losers: usize,
    manifest: String,
    errors: Vec<String>,
}

/// 把单个文件归档到 dest_dir（同名自动加序号避免覆盖）。do_move=true 移动，否则复制。
fn archive_one(src: &str, dest_dir: &std::path::Path, do_move: bool) -> Result<(), String> {
    let src_path = std::path::Path::new(src);
    let name = src_path.file_name().ok_or("无文件名")?;
    std::fs::create_dir_all(dest_dir).map_err(|e| e.to_string())?;

    let mut target = dest_dir.join(name);
    if target.exists() {
        let stem = src_path.file_stem().and_then(|s| s.to_str()).unwrap_or("file");
        let ext = src_path.extension().and_then(|e| e.to_str());
        let mut i = 1;
        loop {
            let candidate = dest_dir.join(match ext {
                Some(e) => format!("{stem} ({i}).{e}"),
                None => format!("{stem} ({i})"),
            });
            if !candidate.exists() {
                target = candidate;
                break;
            }
            i += 1;
        }
    }

    if do_move {
        if std::fs::rename(src_path, &target).is_ok() {
            return Ok(());
        }
        // 跨设备 rename 会失败 → 退回 复制 + 删除
        std::fs::copy(src_path, &target).map_err(|e| e.to_string())?;
        std::fs::remove_file(src_path).map_err(|e| e.to_string())?;
    } else {
        std::fs::copy(src_path, &target).map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// 把用户在擂台的终选写回磁盘：winners/losers 复制或移动到源目录下的子文件夹，
/// 并写一份 keeper-selection.json 清单。mode = copy | move | manifest。
/// 文件系统操作只在 Rust 壳里发生。
#[tauri::command]
async fn archive_decisions(
    winners: Vec<String>,
    losers: Vec<String>,
    mode: String,
) -> Result<ArchiveSummary, String> {
    let first = winners.first().or_else(|| losers.first()).ok_or("没有可归档的裁决")?;
    let base = std::path::Path::new(first)
        .parent()
        .ok_or("无法确定输出目录")?
        .to_path_buf();

    let mut errors = Vec::new();
    let (mut wcount, mut lcount) = (0usize, 0usize);

    if mode != "manifest" {
        let do_move = mode == "move";
        for p in &winners {
            match archive_one(p, &base.join("winners"), do_move) {
                Ok(()) => wcount += 1,
                Err(e) => errors.push(format!("{p}: {e}")),
            }
        }
        for p in &losers {
            match archive_one(p, &base.join("losers"), do_move) {
                Ok(()) => lcount += 1,
                Err(e) => errors.push(format!("{p}: {e}")),
            }
        }
    } else {
        wcount = winners.len();
        lcount = losers.len();
    }

    let manifest_path = base.join("keeper-selection.json");
    let manifest = serde_json::json!({ "winners": winners, "losers": losers, "mode": mode });
    let bytes = serde_json::to_vec_pretty(&manifest).map_err(|e| e.to_string())?;
    if let Err(e) = std::fs::write(&manifest_path, bytes) {
        errors.push(format!("写清单失败: {e}"));
    }

    Ok(ArchiveSummary {
        winners: wcount,
        losers: lcount,
        manifest: manifest_path.to_string_lossy().into_owned(),
        errors,
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![import_photos, archive_decisions])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
