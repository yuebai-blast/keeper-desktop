# 在线升级（auto-update）

本文讲清楚 Keeper 桌面端「打开应用→发现新版→后台下载→重启生效」这套在线升级是怎么搭的，以及**发版前必须做的一次性配置**和**每次发版的固定动作**。

> 打包成安装包的整体流程见 [packaging.md](packaging.md)；发版 tag / workflow 命名规范见仓库根 `monorepo-cicd-naming` 约定。

---

## 1. 机制总览

用的是 **Tauri 2 官方 updater 插件**，四步：

1. **检查**：应用向 `endpoints`（GitHub Release 上的 `latest.json`）拉一份元数据（版本/下载地址/签名）。
2. **比对**：拿 `latest.json` 的 `version` 和**本应用当前版本**（`tauri.conf.json5` 的 `version`）比，决定要不要升。
3. **下载 + 验签**：下载更新包，用配置里的 `pubkey` 验证它确实是我们签发的（防更新源被劫持后推恶意包——**安全命门**）。
4. **安装 + 重启**：原地替换，经 `plugin-process` 的 `relaunch()` 重启生效。

私钥只在 CI secret 里签包，公钥在客户端验包，非对称、不可伪造。

## 2. 代码里已经接好的部分

| 位置 | 作用 |
| :-- | :-- |
| `src-tauri/Cargo.toml` | 引入 `tauri-plugin-updater` / `tauri-plugin-process` |
| `src-tauri/src/lib.rs` | 注册这两个插件 |
| `src-tauri/tauri.conf.json5` → `plugins.updater` | 运行期配置：`pubkey`（待替换）+ `endpoints` |
| `src-tauri/tauri.bundle.conf.json5` → `bundle.createUpdaterArtifacts` | 打包时额外产出带签名的更新包（`.app.tar.gz` / `-setup.exe` + `.sig`） |
| `src-tauri/capabilities/default.json5` | 授权前端用 `updater` + `process:allow-restart` |
| `src/stores/updater.ts` | 检查/下载/安装/重启的状态机（容错：静默检查吞错） |
| `src/components/UpdateBanner.vue` | 顶栏下方非阻塞提示横幅 |
| `src/App.vue` | 启动时**静默检查**（失败不打扰，仅有新版才弹横幅） |
| `src/pages/SettingsPage.vue` | 「版本与更新」区：显示当前版本 + **手动检查更新** |
| `.github/workflows/desktop-release.yml` | 发版 CI：签名构建 + 上传更新包 + 聚合生成 `latest.json` |
| `mise.toml` → `gen-update-keys` | 生成签名密钥对的一次性命令 |

UI 行为：启动静默查一次，有新版才从顶栏滑入横幅（「更新 / 稍后」）；点更新后台下载显示进度，装好提示「立即重启」。设置页另有手动「检查更新」。

## 3. 一次性配置（发版前必须做，否则发版 CI 会失败）

> 现状：`pubkey` 是占位符、签名 secret 未设。在完成下面三步前，发版 workflow 会因「有公钥无私钥」构建失败；但应用其余功能与本地 dev 不受影响（前端检查更新已容错，走「检查失败/暂无更新」分支）。

**① 生成密钥对**（在本机跑一次，会提示设置私钥密码）：

```bash
mise run gen-update-keys
# 产出 ~/.tauri/keeper-updater.key（私钥，妥善保管）与 ~/.tauri/keeper-updater.key.pub（公钥）
```

**② 公钥粘进配置**：把 `~/.tauri/keeper-updater.key.pub` 的**整段内容**填到
`apps/desktop/src-tauri/tauri.conf.json5` 的 `plugins.updater.pubkey`（替换 `REPLACE_WITH_CONTENT_OF_GENERATED_PUBLIC_KEY`）。

**③ 私钥进 GitHub Secrets**（仓库 Settings → Secrets and variables → Actions）：

| Secret 名 | 值 |
| :-- | :-- |
| `TAURI_SIGNING_PRIVATE_KEY` | `~/.tauri/keeper-updater.key` 的**文件内容** |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | 第①步设置的私钥密码（没设则留空） |

> ⚠️ 私钥一旦丢失/泄露，所有已发布客户端将无法验证后续更新（需重发带新公钥的版本让用户手动重装）。务必备份私钥。

## 4. 每次发版的固定动作

1. **改版本号**：把 `apps/desktop/src-tauri/tauri.conf.json5` 的 `version` 改成本次版本（如 `0.4.0`）。
   这是 updater 比对的**唯一权威**——它必须等于 tag 里的版本号，否则版本判断会失准。
   （`package.json` 的 version 与它独立，可一并对齐便于查阅。）
2. **打 tag 发版**：

   ```bash
   git tag desktop-v0.4.0 && git push origin desktop-v0.4.0
   ```

   只触发 `desktop-release.yml`：三平台签名构建 → 上传 `.dmg`/`-setup.exe`（首装）+ `.app.tar.gz`/`-setup.exe`（更新包）+ `.sig` → 聚合任务生成 `latest.json` 上传到同一 Release。
3. 老版本用户下次打开应用即被静默检查命中，弹横幅提示升级。

`latest.json` 里的 `version` 自动取自 tag（去掉 `desktop-v` 前缀），因此第 1 步的 config version 必须与之一致。

## 5. ⚠️ macOS 签名/公证前提（当前未做）

macOS 上 updater 用 `.app.tar.gz` 原地替换。**若 app 未经 Apple Developer ID 签名 + 公证（notarization）**，更新后的 app 可能被 Gatekeeper 拦截（提示「已损坏」或「无法验证开发者」），用户需手动右键打开或移除隔离属性。

- 当前 Keeper **暂无 Apple Developer 证书**，所以本套更新机制虽已接好，但 **macOS 端的「无感升级」体验要等补上 Developer ID 签名 + 公证后才完整**。
- 待有 Apple Developer 账号（$99/年）后，需要：在 CI 注入证书与公证凭据（`APPLE_CERTIFICATE` / `APPLE_ID` / `APPLE_PASSWORD` / `APPLE_TEAM_ID` 等），并在打包时启用签名公证。届时再补本节。
- Windows 端不受此限制（未签名只是首装时有 SmartScreen 提示，更新流程本身可用）。

## 6. 与未来云端中转的关系

当前 `endpoints` 指向 GitHub Release 静态 `latest.json`，零运维，足够 MVP。未来若要做**灰度发布 / 强制更新 / 按授权状态控制更新**，把 `endpoints` 换成自建动态接口即可（可与商业版的云端中转层 `CloudRelayScorer` 共用一层服务），客户端逻辑不变。
