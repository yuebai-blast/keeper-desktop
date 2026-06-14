// 照片库 / 分组 / 层①评分状态的 Pinia store。
import { invoke } from "@tauri-apps/api/core";
import { defineStore } from "pinia";
import { assessGroup, groupPhotos, type Group, type LocalScore, type PhotoError } from "../api";

/** 一个组的层①评分结果。 */
interface GroupAssessment {
  scoresByPath: Record<string, LocalScore>;
  survivorPaths: string[]; // 进层②的候选
  m: number; // 层①保底数
  busy: boolean;
  error: string;
}

interface LibraryState {
  imported: boolean; // 是否已导入并分组
  total: number; // 导入的照片数
  groups: Group[];
  errors: PhotoError[];
  busy: boolean; // 导入/分组进行中
  error: string; // 流程级错误（取消不算）
  assessments: Record<string, GroupAssessment>; // 组 id → 层①评分
}

export const useLibraryStore = defineStore("library", {
  state: (): LibraryState => ({
    imported: false,
    total: 0,
    groups: [],
    errors: [],
    busy: false,
    error: "",
    assessments: {},
  }),
  actions: {
    /** 弹目录选择器（Rust 壳扫图）→ 调 sidecar 分组。用户取消则什么都不做。 */
    async importAndGroup() {
      this.busy = true;
      this.error = "";
      try {
        const paths = await invoke<string[]>("import_photos");
        if (paths.length === 0) return; // 取消或空目录
        this.total = paths.length;
        const res = await groupPhotos(paths);
        this.groups = res.groups;
        this.errors = res.errors;
        this.imported = true;
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.busy = false;
      }
    },
    /** 对一个组做层① 本地评分，结果存入 assessments[组id]。 */
    async assessGroup(group: Group) {
      this.assessments[group.id] = { scoresByPath: {}, survivorPaths: [], m: 0, busy: true, error: "" };
      const a = this.assessments[group.id];
      try {
        const res = await assessGroup(group.id, group.photos);
        for (const s of res.scores) a.scoresByPath[s.path] = s;
        a.survivorPaths = res.survivors.map((s) => s.path);
        a.m = res.m;
      } catch (e) {
        a.error = e instanceof Error ? e.message : String(e);
      } finally {
        a.busy = false;
      }
    },
    reset() {
      this.imported = false;
      this.total = 0;
      this.groups = [];
      this.errors = [];
      this.error = "";
      this.assessments = {};
    },
  },
});
