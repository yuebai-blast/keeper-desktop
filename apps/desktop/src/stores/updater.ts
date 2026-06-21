// 在线升级（updater）状态的 Pinia store。
//
// 机制：经 @tauri-apps/plugin-updater 的 check() 向 tauri.conf 里配置的 endpoints 拉 latest.json，
// 与本应用当前版本比对；有新版则 downloadAndInstall（下载→用 pubkey 验签→原地替换），
// 装好后用 @tauri-apps/plugin-process 的 relaunch() 重启生效。
//
// 容错：未配真实 pubkey / 无网络 / 该平台暂无发布时，check() 会抛错或返回 null。
// 启动时的「静默检查」吞掉错误只记日志，绝不打扰用户；设置页的「手动检查」才把结果/错误显式呈现。
import { defineStore } from "pinia";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

// 当前待安装的 Update 句柄（plugin 返回的实例，非响应式，单独存模块变量）。
let pending: Update | null = null;

type Phase =
  | "idle" // 未检查 / 检查过无更新
  | "checking" // 正在检查
  | "available" // 发现新版，待用户决定是否更新
  | "downloading" // 正在下载安装
  | "ready" // 已装好，待重启
  | "error"; // 检查/下载失败

interface UpdaterState {
  phase: Phase;
  version: string; // 新版本号
  notes: string; // 更新说明
  percent: number; // 下载进度 0~100
  error: string; // 失败信息（仅手动检查时呈现）
  dismissed: boolean; // 用户是否已关掉本次更新提示横幅
}

export const useUpdaterStore = defineStore("updater", {
  state: (): UpdaterState => ({
    phase: "idle",
    version: "",
    notes: "",
    percent: 0,
    error: "",
    dismissed: false,
  }),
  getters: {
    // 是否应展示「发现新版」横幅（有更新、未被关掉、且不在下载/装好态）
    showBanner: (s): boolean => s.phase === "available" && !s.dismissed,
    busy: (s): boolean => s.phase === "checking" || s.phase === "downloading",
  },
  actions: {
    /**
     * 检查更新。
     * @param silent true=启动静默检查（吞错、不报「已是最新」）；false=手动检查（显式呈现结果与错误）。
     */
    async check(silent = false) {
      if (this.busy) return;
      this.error = "";
      this.phase = "checking";
      try {
        const update = await check();
        if (update) {
          pending = update;
          this.version = update.version;
          this.notes = update.body ?? "";
          this.dismissed = false;
          this.phase = "available";
        } else {
          pending = null;
          // 手动检查回到 idle（由设置页提示「已是最新」）；静默检查同样回 idle，不打扰
          this.phase = "idle";
        }
      } catch (e) {
        pending = null;
        const msg = e instanceof Error ? e.message : String(e);
        if (silent) {
          // 启动静默检查失败（无网/未配 pubkey/无该平台发布）不打扰用户，仅记日志
          console.warn("[updater] 静默检查更新失败：", msg);
          this.phase = "idle";
        } else {
          this.error = msg;
          this.phase = "error";
        }
      }
    },

    /** 下载并安装当前待装更新，进度回写 percent，装好后置 ready。 */
    async downloadAndInstall() {
      if (!pending || this.phase === "downloading") return;
      this.error = "";
      this.phase = "downloading";
      this.percent = 0;
      let total = 0;
      let got = 0;
      try {
        await pending.downloadAndInstall((event) => {
          switch (event.event) {
            case "Started":
              total = event.data.contentLength ?? 0;
              break;
            case "Progress":
              got += event.data.chunkLength;
              this.percent = total > 0 ? Math.min(100, Math.round((got / total) * 100)) : 0;
              break;
            case "Finished":
              this.percent = 100;
              break;
          }
        });
        this.phase = "ready";
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
        this.phase = "error";
      }
    },

    /** 重启应用以加载新版（更新装好后调用）。 */
    async restart() {
      await relaunch();
    },

    /** 关掉本次更新提示横幅（不影响设置页手动再查）。 */
    dismiss() {
      this.dismissed = true;
    },
  },
});
