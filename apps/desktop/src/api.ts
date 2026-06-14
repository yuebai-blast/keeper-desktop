// Keeper 推理 sidecar 的 HTTP 客户端。
// 本机服务，默认 127.0.0.1:8761（mise run sidecar 启动）。可由 VITE_SIDECAR_URL 覆盖。

const BASE = import.meta.env.VITE_SIDECAR_URL ?? "http://127.0.0.1:8761";

/** /health 返回：模型就绪态。 */
export interface Health {
  status: "loading" | "ready" | "error" | string;
  version: string;
  detail: string;
}

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status} ${resp.statusText}`);
  }
  return resp.json() as Promise<T>;
}

/** 查询 sidecar 健康/就绪状态。连不上会抛错（服务没起）。 */
export function getHealth(): Promise<Health> {
  return get<Health>("/health");
}

/** 一个「瞬间组」。 */
export interface Group {
  id: string;
  photos: string[];
}

export interface PhotoError {
  path: string;
  error: string;
}

export interface GroupResponse {
  groups: Group[];
  errors: PhotoError[];
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status} ${resp.statusText}`);
  }
  return resp.json() as Promise<T>;
}

/** 把一批照片路径分成「瞬间组」（DINOv2 语义 + 时间）。 */
export function groupPhotos(photos: string[]): Promise<GroupResponse> {
  return post<GroupResponse>("/group", { photos });
}

/** 缩略图直链（供 <img src>，由 sidecar 解码/缩放，支持 RAW/HEIC）。 */
export function thumbnailUrl(path: string, size = 256): string {
  return `${BASE}/thumbnail?path=${encodeURIComponent(path)}&size=${size}`;
}

// ── 层① 本地评分 ──────────────────────────────────────────────────────────

export interface Penalty {
  reason: string;
  points: number;
}

/** 层① 单张评分明细（与 sidecar ScoreDetail 对齐，字段供前端透明展示）。 */
export interface ScoreDetail {
  base: number;
  tech_quality: number;
  tech_source: string;
  clipiqa: number;
  sharpness: number | null;
  sharpness_norm: number;
  entropy: number;
  brightness_mean: number;
  contrast: number;
  underexposed_ratio: number;
  overexposed_ratio: number;
  penalties: Penalty[];
}

export interface LocalScore {
  path: string;
  score: number;
  primary_reason: string;
  detail: ScoreDetail | null;
}

export interface SurvivorEntry {
  path: string;
  score: number;
  origin: "passed" | "quota_fill" | string;
}

export interface AssessResponse {
  group_id: string;
  scores: LocalScore[];
  survivors: SurvivorEntry[];
  n: number;
  m: number;
  errors: PhotoError[];
}

/** 对一个组做层① 本地评分（每张 0–100 + 漏斗收口出 survivors）。 */
export function assessGroup(groupId: string, photos: string[]): Promise<AssessResponse> {
  return post<AssessResponse>("/assess", {
    group_id: groupId,
    photos: photos.map((path) => ({ path })),
  });
}
