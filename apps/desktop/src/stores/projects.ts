// 项目工作流的 Pinia store。状态权威在 sidecar（sqlite 持久化），这里只缓存当前视图，
// 每个写操作后用服务端返回的最新视图刷新——保证「随时退出、随时恢复」。
import { defineStore } from "pinia";
import {
  assessProjectGroup,
  completeProject,
  confirmAll,
  confirmGroup,
  createProject,
  deleteProject,
  getGroup,
  getProject,
  groupProject,
  ignoreFailures,
  listProjects,
  pkChoose,
  pkStart,
  pkUndo,
  previewFolder,
  retryGroup,
  updateSelection,
  type CompleteResult,
  type GroupDetail,
  type PkOutcome,
  type PkView,
  type ProjectDetail,
  type ProjectPreview,
  type ProjectView,
  type Selection,
  type SelectionChange,
} from "../api";
import { useEngineStore } from "./engine";

interface ProjectsState {
  list: ProjectView[];
  detail: ProjectDetail | null; // 当前项目（含各组摘要）
  group: GroupDetail | null; // 当前打开的组详情
  busy: boolean;
  error: string;
}

export const useProjectsStore = defineStore("projects", {
  state: (): ProjectsState => ({
    list: [],
    detail: null,
    group: null,
    busy: false,
    error: "",
  }),
  getters: {
    /** 是否全部分组都已确认（可提交完成）。 */
    allConfirmed: (s): boolean =>
      !!s.detail &&
      s.detail.groups.length > 0 &&
      s.detail.groups.every((g) => g.status === "CONFIRMED"),
  },
  actions: {
    /** 统一的错误处理：记录文案 + 503 时触发模型修复页。 */
    _fail(e: unknown) {
      this.error = e instanceof Error ? e.message : String(e);
      useEngineStore().reportError(e);
      throw e;
    },

    async loadProjects() {
      this.busy = true;
      this.error = "";
      try {
        this.list = await listProjects();
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.busy = false;
      }
    },

    /** 删除项目（清理副本 + 数据库资源），成功后从本地列表移除。 */
    async remove(id: number) {
      this.busy = true;
      this.error = "";
      try {
        await deleteProject(id);
        this.list = this.list.filter((p) => p.id !== id);
      } catch (e) {
        this._fail(e);
      } finally {
        this.busy = false;
      }
    },

    /** 预览源文件夹（不建项目）；交给页面展示。 */
    async preview(folder: string): Promise<ProjectPreview> {
      this.error = "";
      try {
        return await previewFolder(folder);
      } catch (e) {
        return this._fail(e);
      }
    },

    /** 新建项目并复制副本，返回新项目。 */
    async create(name: string, sourceFolder: string): Promise<ProjectView> {
      this.busy = true;
      this.error = "";
      try {
        return await createProject(name, sourceFolder);
      } catch (e) {
        return this._fail(e);
      } finally {
        this.busy = false;
      }
    },

    async loadProject(id: number) {
      this.busy = true;
      this.error = "";
      try {
        this.detail = await getProject(id);
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.busy = false;
      }
    },

    /** 分组（幂等：已分组则原样返回）。 */
    async runGroup(id: number) {
      this.busy = true;
      this.error = "";
      try {
        this.detail = await groupProject(id);
      } catch (e) {
        this._fail(e);
      } finally {
        this.busy = false;
      }
    },

    async loadGroup(id: number, gk: string) {
      this.busy = true;
      this.error = "";
      try {
        this.group = await getGroup(id, gk);
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.busy = false;
      }
    },

    /** 层①+层②评测（需模型就绪/大模型可用）。 */
    async assess(id: number, gk: string) {
      this.busy = true;
      this.error = "";
      try {
        this.group = await assessProjectGroup(id, gk);
      } catch (e) {
        this._fail(e);
      } finally {
        this.busy = false;
      }
    },

    async retry(id: number, gk: string, photoId?: number) {
      this.busy = true;
      this.error = "";
      try {
        this.group = await retryGroup(id, gk, photoId);
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.busy = false;
      }
    },
    async ignoreFailures(id: number, gk: string, photoId?: number) {
      this.error = "";
      try {
        this.group = await ignoreFailures(id, gk, photoId);
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      }
    },

    async setSelection(id: number, gk: string, changes: SelectionChange[]) {
      try {
        this.group = await updateSelection(id, gk, changes);
      } catch (e) {
        this._fail(e);
      }
    },

    /** 切换单张去留。 */
    toggleSelection(id: number, gk: string, photoId: number, selection: Selection) {
      return this.setSelection(id, gk, [{ photo_id: photoId, selection }]);
    },

    /** 从未通过救回（标记 rescued，便于进 PK 池）。 */
    rescue(id: number, gk: string, photoId: number, rescued: boolean) {
      return this.setSelection(id, gk, [{ photo_id: photoId, rescued }]);
    },

    async confirmGroup(id: number, gk: string) {
      try {
        this.group = await confirmGroup(id, gk);
        await this.loadProject(id); // 同步分组列表里的状态
      } catch (e) {
        this._fail(e);
      }
    },

    async confirmAll(id: number) {
      this.busy = true;
      this.error = "";
      try {
        this.detail = await confirmAll(id);
      } catch (e) {
        this._fail(e);
      } finally {
        this.busy = false;
      }
    },

    async complete(id: number): Promise<CompleteResult> {
      this.busy = true;
      this.error = "";
      try {
        return await completeProject(id);
      } catch (e) {
        return this._fail(e);
      } finally {
        this.busy = false;
      }
    },

    // ── PK ──────────────────────────────────────────────────────────────
    async pkStart(id: number, gk: string, pool: string[], restart = false): Promise<PkView> {
      try {
        return await pkStart(id, gk, pool, restart);
      } catch (e) {
        return this._fail(e);
      }
    },
    async pkChoose(id: number, gk: string, outcome: PkOutcome): Promise<PkView> {
      try {
        return await pkChoose(id, gk, outcome);
      } catch (e) {
        return this._fail(e);
      }
    },
    async pkUndo(id: number, gk: string): Promise<PkView> {
      try {
        return await pkUndo(id, gk);
      } catch (e) {
        return this._fail(e);
      }
    },
  },
});
