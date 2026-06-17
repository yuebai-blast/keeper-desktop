# 打包与部署

本文讲清楚怎么把 Keeper 从源码变成用户能双击安装的**安装包**（专业说法：**bundling / 打包**，产物叫 **installer / bundle**）。面向「几乎不懂 Tauri」的读者，重点是「打成安装包」这一步。

> 想先了解整体架构，看 [architecture.md](architecture.md)；想了解工程分层与契约，看 [tech-overview.md](tech-overview.md)。

---

## 1. 先建立几个概念

Keeper 是 monorepo，运行时由**两个进程**组成：

| 进程 | 是什么 | 打包时怎么处理 |
| :-- | :-- | :-- |
| 桌面应用（壳 + 前端） | Tauri 2（Rust 编译出的原生程序）里嵌了 Vue 前端 | 编成平台原生可执行 + 安装包 |
| sidecar（推理服务） | 一个 Python FastAPI 服务 | 用 PyInstaller **冻结成单个二进制**，再作为「外部二进制」塞进安装包 |

**关键难点**：用户机器上没有 Python 环境，也没有 pnpm/cargo。所以我们必须把 Python 服务连同它的一大堆依赖（torch、onnxruntime、insightface、pyiqa、opencv…）**冻结成一个不依赖系统 Python 的独立可执行文件**，再让 Tauri 把它当作 **sidecar（externalBin）** 一起打进安装包。安装后由 Rust 壳在启动时自动拉起它。

### Tauri 的 sidecar / externalBin 机制（务必理解）

- 「sidecar」是 Tauri 的术语：随你的应用一起分发、由你的应用启动的**外部可执行程序**。
- 在配置里你只写**基名** `binaries/keeper-sidecar`；Tauri 打包时会自动去找按当前平台 **target triple**（目标三元组）后缀命名的真实文件。
  - 例：macOS Apple Silicon 上要找 `binaries/keeper-sidecar-aarch64-apple-darwin`
  - Windows x64 上要找 `binaries/keeper-sidecar-x86_64-pc-windows-msvc.exe`
- 这个带后缀的文件由我们用 PyInstaller 产出后**改名落位**到 `apps/desktop/src-tauri/binaries/`。
- 安装后，Rust 壳用 `app.shell().sidecar("keeper-sidecar")` 把它拉起（仅 release 构建，见 `src-tauri/src/lib.rs`）。
- 这条链路要能成立，还需要在 `capabilities/default.json5` 里**显式授权** `shell:allow-spawn`（Tauri 2 默认不给任何原生能力）。

---

## 2. 一条命令打包

工具链与命令统一由 **mise** 管理。装好工具链后，**打安装包只要一条命令**：

```bash
mise install        # 一次性：装钉死版本的 python / uv / node / pnpm / rust
mise run install    # 一次性：同步 sidecar(uv) + desktop(pnpm) 依赖
mise run package    # 打包：冻结 sidecar → 落位 binaries → tauri build 出安装包
```

产物在 `apps/desktop/src-tauri/target/release/bundle/` 下（具体见 [§4](#4-产物在哪)）。

`mise run package` 串了三步（定义在 `mise.toml` 的 `[tasks.package]`）：

```bash
mise run bundle-sidecar     # ① PyInstaller 冻结 sidecar
mise run stage-sidecar      # ② 按 target triple 改名，放进 binaries/
pnpm tauri build --config src-tauri/tauri.bundle.conf.json5   # ③ 出安装包
```

下面逐步拆解。

---

## 3. 三步拆解

### 步骤 ① 冻结 sidecar（`mise run bundle-sidecar`）

```bash
# 等价于（在 sidecar/ 下）：
uv run pyinstaller keeper-sidecar.spec --noconfirm --clean
```

- 入口是 `sidecar/entry.py`（冻结后没有 `python -m` 的概念，所以用显式入口调 `keeper_engine.main:main`）。
- 配方在 `sidecar/keeper-sidecar.spec`：用 `collect_all` 把 torch / onnxruntime / insightface / pyiqa / cv2 / rawpy 等的子模块和数据文件全收进来；`dependency_injector` 是 Cython 扩展、静态分析探测不到，需显式 collect。
- **模型权重不打包**：运行时首启会下载到 `~/.keeper/models`，保持安装包体积可控。
- 产物：`sidecar/dist/keeper-sidecar`（单文件，`onefile=True`）。

> 这一步最容易出问题（漏 hidden import / 缺数据文件）。改了 sidecar 依赖后，单独跑 `mise run bundle-sidecar` 再手动执行 `sidecar/dist/keeper-sidecar --port 8761` 验证能起来，比每次全量打包快得多。

### 步骤 ② 落位到 binaries/（`mise run stage-sidecar`）

把上一步的单文件按当前机器的 target triple 改名，放到 Tauri 约定目录：

```bash
TRIPLE=$(rustc -vV | sed -n 's/host: //p')      # 当前平台三元组，如 aarch64-apple-darwin
cp sidecar/dist/keeper-sidecar \
   apps/desktop/src-tauri/binaries/keeper-sidecar-$TRIPLE      # Windows 会带 .exe
```

> `binaries/` 目录里的实际二进制是构建产物，**不入库**（仓库里只保留空目录占位）。

### 步骤 ③ tauri build 出安装包

```bash
pnpm tauri build --config src-tauri/tauri.bundle.conf.json5
```

`tauri build` 做了三件事：

1. 跑 `beforeBuildCommand`（`pnpm build`）把前端编成 `apps/desktop/dist/` 静态资源；
2. 用 cargo **release** 模式编译 Rust 壳，把前端资源和 sidecar 二进制一起嵌入；
3. 按 `bundle.targets` 调用各平台打包器，产出安装包。

**为什么这里要带 `--config tauri.bundle.conf.json5`？** 见下一节。

---

## 4. 两个配置文件：为什么拆开

打包相关的配置刻意拆成两份：

| 文件 | 何时加载 | 装了什么 |
| :-- | :-- | :-- |
| `src-tauri/tauri.conf.json5` | dev 和打包都加载（根配置） | 应用名/版本/窗口/图标/bundle 基础设置，**不含 externalBin** |
| `src-tauri/tauri.bundle.conf.json5` | **仅打包**时用 `--config` 合并 | 只有 `bundle.externalBin`（把 sidecar 打进来） |

`--config` 会把后者**合并**到前者之上（字段冲突以 `--config` 为准）。

**为什么不把 externalBin 直接写进根配置？**
因为 externalBin 一旦写进根配置，`mise run app`（本地 dev）启动时 Tauri 会**强制要求** `binaries/` 下存在按 triple 命名的二进制，否则直接报错。而 dev 时 sidecar 是用 `mise run sidecar` 单独跑的、`binaries/` 是空的。把 externalBin 隔离到打包专用配置后，**本地 dev 零二进制依赖**，不必每次先冻结 sidecar。

> 对应地，Rust 壳里也用 `if !cfg!(debug_assertions)` 区分：只有 release（打包）构建才自动拉起内置 sidecar；dev 构建不拉，交给 `mise run sidecar`。

---

## 5. 产物在哪

`tauri build` 完成后会打印每个安装包的绝对路径。产物根目录：

```
apps/desktop/src-tauri/target/release/bundle/
```

各平台产物（由 `tauri.conf.json5` 的 `bundle.targets: "all"` 决定，会生成当前平台支持的全部格式）：

| 平台 | 子目录 / 产物 | 说明 |
| :-- | :-- | :-- |
| macOS | `macos/Keeper.app` | 可直接运行的应用包 |
| macOS | `dmg/Keeper_0.1.0_aarch64.dmg` | 拖拽安装的磁盘镜像，**分发用这个** |
| Windows | `nsis/Keeper_0.1.0_x64-setup.exe` | NSIS 安装向导 |
| Windows | `msi/Keeper_0.1.0_x64_en-US.msi` | MSI 安装包 |
| Linux | `deb/`、`appimage/`、`rpm/` | Debian 包 / AppImage / RPM |

---

## 6. 跨平台：只能在目标系统上打

**Tauri 不做开箱即用的交叉编译**：要出 macOS 安装包就得在 macOS 上打，要 Windows 的 `.exe` 就得在 Windows 上打。原因有二：

1. Rust 壳要链接各平台原生 GUI 库（macOS 用 WebKit，Windows 用 WebView2）；
2. 我们的 sidecar 是用 PyInstaller 在**当前系统**冻结的，天然只跑当前系统。

所以多平台发布通常靠 CI（每个目标系统一个 runner）分别跑 `mise run package`。本机只能产出本机平台的包。

---

## 7. 签名与公证（对外分发才需要）

自己机器上跑、或内部测试，可以跳过本节。**要分发给真实用户**时：

- **macOS**：未签名/未公证的 `.app` 用户首次打开会被 Gatekeeper 拦（提示「无法打开，因为无法验证开发者」）。正式分发需要 Apple Developer 证书做**签名 + 公证（notarization）**。Tauri 支持在 `bundle.macOS` 配置签名身份，并通过环境变量提供 Apple 凭据。
- **Windows**：未签名的安装包会触发 SmartScreen 警告。正式分发需要代码签名证书（OV/EV）。

> 这些属于「对外发布」环节，当前 MVP 未配置。真要做时再在 `tauri.conf.json5` 的 `bundle` 段补 `macOS` / `windows` 子配置，并把证书/凭据通过环境变量注入（**绝不入库**）。

---

## 8. 排错速查

| 现象 | 多半原因 / 处理 |
| :-- | :-- |
| `tauri build` 报找不到 `keeper-sidecar-<triple>` | 步骤 ② 没跑或 triple 不对；重跑 `mise run stage-sidecar`，确认 `binaries/` 里有对应文件 |
| 安装后应用能开但功能转圈、连不上 sidecar | sidecar 没起来。看应用日志里 `[sidecar]` 开头的行（lib.rs 把 sidecar 的 stdout/stderr 转发了）；多半是 PyInstaller 漏了依赖 |
| PyInstaller 冻结成功但单跑报 `ModuleNotFoundError` | 漏 hidden import；在 `keeper-sidecar.spec` 的 `collect_all` 列表或 `hiddenimports` 里补上，重跑 `mise run bundle-sidecar` |
| dev（`mise run app`）报缺 externalBin | externalBin 被误写进了根配置；它应只在 `tauri.bundle.conf.json5` 里 |
| 改了配置但不生效 | 确认改的是 `.json5` 文件；JSON5（带注释）需要 `Cargo.toml` 里给 `tauri`/`tauri-build` 开了 `config-json5` feature |

---

## 9. 涉及的文件一览

| 文件 | 角色 |
| :-- | :-- |
| `mise.toml` | `bundle-sidecar` / `stage-sidecar` / `package` 三个 task 的定义 |
| `sidecar/keeper-sidecar.spec` | PyInstaller 冻结配方 |
| `sidecar/entry.py` | 冻结入口 |
| `apps/desktop/src-tauri/tauri.conf.json5` | Tauri 根配置（应用名/版本/窗口/图标/bundle 基础） |
| `apps/desktop/src-tauri/tauri.bundle.conf.json5` | 打包专用：externalBin（sidecar） |
| `apps/desktop/src-tauri/capabilities/default.json5` | 授权 `shell:allow-spawn` 拉起 sidecar |
| `apps/desktop/src-tauri/Cargo.toml` | 开 `config-json5` feature；声明壳依赖/插件 |
| `apps/desktop/src-tauri/src/lib.rs` | release 构建下自动拉起内置 sidecar |
