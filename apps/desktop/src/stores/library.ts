// 照片库 / 分组 / 层①评分状态的 Pinia store。
import { invoke } from "@tauri-apps/api/core";
import { defineStore } from "pinia";
import { assessGroup, groupPhotos, type Group, type LocalScore, type PhotoError } from "../api";
import { useEngineStore } from "./engine";

/** 一个组的层①评分结果。 */
interface GroupAssessment {
  scoresByPath: Record<string, LocalScore>;
  survivorPaths: string[]; // 进层②的候选
  m: number; // 层①保底数
  busy: boolean;
  error: string;
}

/** 用户在擂台上对一个组的终选结果。 */
interface GroupDecision {
  winner: string | null; // 胜出留存的那张；整组舍弃时为 null
  losers: string[]; // 被淘汰的
}

/** 归档（写回磁盘）结果，与 Rust archive_decisions 的 ArchiveSummary 对齐。 */
export interface ArchiveSummary {
  winners: number;
  losers: number;
  manifest: string;
  errors: string[];
}

export type ArchiveMode = "copy" | "move" | "manifest";

interface LibraryState {
  imported: boolean; // 是否已导入并分组
  total: number; // 导入的照片数
  groups: Group[];
  errors: PhotoError[];
  busy: boolean; // 导入/分组进行中
  error: string; // 流程级错误（取消不算）
  assessments: Record<string, GroupAssessment>; // 组 id → 层①评分
  decisions: Record<string, GroupDecision>; // 组 id → 擂台终选
  archiving: boolean;
  archiveSummary: ArchiveSummary | null;
  archiveError: string;
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
    decisions: {},
    archiving: false,
    archiveSummary: null,
    archiveError: "",
  }),
  getters: {
    /** 进擂台的候选：评过分用层①幸存者，否则用全组照片。 */
    candidatesOf: (s) => (group: Group): string[] => {
      const survivors = s.assessments[group.id]?.survivorPaths;
      return survivors && survivors.length ? survivors : group.photos;
    },
    /** 已裁决的组数。 */
    decidedCount: (s): number => Object.keys(s.decisions).length,
  },
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
        useEngineStore().reportError(e); // 模型不可用(503) → 进修复页
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
        useEngineStore().reportError(e); // 模型不可用(503) → 进修复页
      } finally {
        a.busy = false;
      }
    },
    /** 记录某组的擂台终选结果。 */
    decideGroup(groupId: string, winner: string | null, losers: string[]) {
      this.decisions[groupId] = { winner, losers };
    },
    /** 把所有裁决写回磁盘（Rust 壳做 FS 操作）。mode: copy / move / manifest。 */
    async archive(mode: ArchiveMode) {
      const winners: string[] = [];
      const losers: string[] = [];
      for (const d of Object.values(this.decisions)) {
        if (d.winner) winners.push(d.winner);
        losers.push(...d.losers);
      }
      if (!winners.length && !losers.length) return;
      this.archiving = true;
      this.archiveError = "";
      this.archiveSummary = null;
      try {
        this.archiveSummary = await invoke<ArchiveSummary>("archive_decisions", { winners, losers, mode });
      } catch (e) {
        this.archiveError = e instanceof Error ? e.message : String(e);
      } finally {
        this.archiving = false;
      }
    },
    reset() {
      this.imported = false;
      this.total = 0;
      this.groups = [];
      this.errors = [];
      this.error = "";
      this.assessments = {};
      this.decisions = {};
      this.archiveSummary = null;
      this.archiveError = "";
    },
  },
});
