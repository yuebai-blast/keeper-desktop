// Keeper 推理 sidecar 的 HTTP 客户端。
// 本机服务，默认 127.0.0.1:8761（mise run sidecar 启动）。可由 VITE_SIDECAR_URL 覆盖。

const BASE = import.meta.env.VITE_SIDECAR_URL ?? "http://127.0.0.1:8761";

/** 模型加载进度。 */
export interface Progress {
  current: number; // 正在加载的步骤序号（1-based）
  total: number; // 总步骤数
  step: string; // 当前正在加载的模块名
  downloaded_mb: number; // 本轮已下载量（MB）
  speed_mbps: number; // 实时下载速度（MB/s）
  percent: number; // 估算总进度百分比
}

/** /health 返回：模型就绪态 + 加载进度。 */
export interface Health {
  status: "awaiting_consent" | "loading" | "ready" | "error" | string;
  version: string;
  detail: string;
  retryable: boolean; // error 时是否可重试（依赖缺失=false）
  first_run: boolean; // 是否首次（模型缓存为空、需联网下载）
  expected_total_mb: number; // 首次下载预估总体量（MB），用于确认弹窗告知用户
  progress: Progress;
}

/** 统一响应结构体（与 sidecar ApiResponse 对齐）：恒 HTTP 200，业务成败看 code。 */
export interface ApiResponse<T> {
  code: number; // 0=成功，非 0 见 BizCode
  data: T | null;
  msg: string | null;
}

/** 业务错误码（镜像 sidecar enumeration/biz_code.py，改任一端两边同步）。 */
export const BizCode = {
  SUCCESS: 0,
  INTERNAL_ERROR: 110001,
  VALIDATION_ERROR: 110002,
  MODEL_NOT_READY: 210001,
  MODEL_DEPENDENCY_MISSING: 210002,
  SCORER_FAILED: 310001,
  PROJECT_NAME_DUPLICATE: 410001,
  PROJECT_NOT_FOUND: 410002,
  GROUP_NOT_FOUND: 410003,
  INVALID_PROJECT_NAME: 410004,
  NO_IMPORTABLE_IMAGES: 410005,
  INVALID_SOURCE_FOLDER: 410006,
  GROUPS_NOT_ALL_CONFIRMED: 410007,
  GROUP_HAS_UNRESOLVED_FAILURES: 410008,
} as const;

/** 业务错误：携带业务码 code（供前端区分「模型未就绪 210001」以进修复页）。 */
export class ApiError extends Error {
  code: number;
  constructor(code: number, message: string) {
    super(message);
    this.code = code;
  }
}

/** 解析统一响应：code===0 返回 data，否则抛 ApiError；非 JSON/网络异常兜底为内部错误。 */
async function unwrap<T>(resp: Response): Promise<T> {
  let body: ApiResponse<T>;
  try {
    body = (await resp.json()) as ApiResponse<T>;
  } catch {
    // 非 JSON（如框架层 500/404）——兜底成内部错误。
    throw new ApiError(BizCode.INTERNAL_ERROR, `${resp.status} ${resp.statusText}`);
  }
  if (body.code !== BizCode.SUCCESS) {
    throw new ApiError(body.code, body.msg ?? `错误码 ${body.code}`);
  }
  return body.data as T;
}

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  return unwrap<T>(resp);
}

/** 查询 sidecar 健康/就绪状态。连不上会抛错（服务没起）。 */
export function getHealth(): Promise<Health> {
  return get<Health>("/health");
}

/** 用户同意首次下载模型（仅在 awaiting_consent 时生效，触发下载）。返回最新就绪态。 */
export function consentWarmup(): Promise<Health> {
  return post<Health>("/warmup/consent", {});
}

/** 重新预热模型（仅在可重试的 error 时生效，用于下载失败重试）。返回最新就绪态。 */
export function retryWarmup(): Promise<Health> {
  return post<Health>("/warmup/retry", {});
}

/** 强制重新加载模型（运行时模型不可用时的修复入口）。返回最新就绪态。 */
export function reloadModels(): Promise<Health> {
  return post<Health>("/warmup/reload", {});
}

/** 大模型配置（自用版设置页）。**绝不含 key/AK/SK 明文**，只用布尔位标识是否已配置。 */
export interface AppSettings {
  ark_model: string; // Ark 模型 id
  ark_base_url: string; // Ark 兼容接口基址
  ark_concurrency: number; // 打分并发数
  ark_key_set: boolean; // 是否已配置 key
  volc_credentials_set: boolean; // 是否已配置火山 AK/SK（用于拉取视觉模型）
}

/** 更新大模型配置（部分更新；字段缺省=不动。ark_key 留空=保持原 key 不变）。 */
export interface SettingsUpdate {
  ark_key?: string;
  ark_model?: string;
  ark_base_url?: string;
}

/** 拉取到的视觉模型（支持图片理解）。 */
export interface VisionModel {
  model_id: string; // 推理用 model id（模型名-主版本）
  name: string; // 基础模型名称
  version: string; // 主版本号
  display_name: string; // 展示名
}

/** 拉取视觉模型请求；AK/SK 留空=用已存的（env/文件）。 */
export interface ListVisionModelsBody {
  volc_ak?: string;
  volc_sk?: string;
}

/** 读取当前大模型配置（不含 key 明文）。 */
export const getSettings = () => get<AppSettings>("/settings");

/** 测试大模型连接（不落配置）；连不上抛 ApiError（SCORER_FAILED，msg 含详情）。 */
export const testSettings = (body: SettingsUpdate) => post<AppSettings>("/settings/test", body);

/** 保存大模型配置（后端先测后存）；返回更新后的快照。 */
export const saveSettings = (body: SettingsUpdate) => post<AppSettings>("/settings", body);

/** 用火山 AK/SK 拉取支持图片理解的模型列表（辅助选 model id）；成功后 AK/SK 会落盘复用。 */
export const listVisionModels = (body: ListVisionModelsBody) =>
  post<{ items: VisionModel[] }>("/settings/models", body);

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
  return unwrap<T>(resp);
}

async function del<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, { method: "DELETE" });
  return unwrap<T>(resp);
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
  origin: "PASSED" | "QUOTA_FILL" | string;
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

// ── 项目工作流（持久化在 sidecar，与 controller/project_controller 对齐）──────────

export type ProjectStatus = "GROUPING" | "SELECTING" | "COMPLETED" | string;
export type GroupStatus = "PENDING" | "ASSESSED" | "CONFIRMED" | string;
export type Selection = "KEPT" | "DISCARDED";
export type PkOutcome = "PICK_LEFT" | "PICK_RIGHT" | "KEEP_BOTH" | "DROP_BOTH";

/** 源文件夹预览：数量、拍摄时间范围、拍摄地（尽力而为，可空）。 */
export interface ProjectPreview {
  count: number;
  time_start: string | null;
  time_end: string | null;
  location: string | null;
  errors: PhotoError[];
}

/** 项目视图。 */
export interface ProjectView {
  id: number;
  name: string;
  source_folder: string;
  workspace_dir: string;
  target_dir: string;
  status: ProjectStatus;
  photo_count: number;
  time_start: string | null;
  time_end: string | null;
  location: string | null;
  created_at: string;
  completed_at: string | null;
}

/** 分组列表里的一组摘要。 */
export interface GroupSummary {
  group_key: string;
  location: string | null;
  time_start: string | null;
  time_end: string | null;
  status: GroupStatus;
  photo_count: number;
  kept_count: number;
  failed_count: number; // 评测失败且未忽略的张数（>0 时本组裁决被锁）
  photo_paths: string[]; // 组内照片的 workspace 路径（供列表页缩略图预览）
  photo_names: string[]; // 与 photo_paths 平行：原始相对路径（带原文件名，供展示）
}

/** 组详情/PK 里的一张照片完整信息（层①必有，层②有则展示）。 */
export interface PhotoView {
  id: number;
  workspace_path: string;
  original_path: string;
  filename: string;
  capture_time: string | null;
  location: string | null;
  group_key: string | null;
  local_score: number | null;
  local_detail: ScoreDetail | null;
  llm_score: number | null;
  llm_reason: string;
  llm_flaws: string;
  llm_editable: "READY" | "WORTH_EDITING" | "NOT_WORTH" | "UNFIXABLE" | "";
  llm_edit_advice: string;
  origin: "PASSED" | "QUOTA_FILL" | null;
  selection: Selection | null;
  rescued: boolean;
  assess_status: "NOT_ASSESSED" | "SUCCESS" | "LAYER1_FAILED" | "LAYER2_FAILED" | string;
  assess_error: string | null;
  assess_error_ignored: boolean;
}

/** PK 进度视图。current 为当前一对的 workspace 路径。 */
export interface PkView {
  current: string[] | null;
  pool_remaining: number;
  kept_aside: string[];
  done: boolean;
  can_undo: boolean;
}

export interface ProjectDetail {
  project: ProjectView;
  groups: GroupSummary[];
}

export interface GroupDetail {
  project_id: number;
  group: GroupSummary;
  photos: PhotoView[];
  pk: PkView | null;
  errors: PhotoError[];
}

export interface CompleteResult {
  output_dir: string;
  kept_count: number;
}

export interface SelectionChange {
  photo_id: number;
  selection?: Selection | null;
  rescued?: boolean | null;
}

const enc = encodeURIComponent;

/** 预览源文件夹（不建项目）。 */
export const previewFolder = (folder: string) =>
  post<ProjectPreview>("/projects/preview", { folder });

/** 新建项目（校验名唯一 → 复制副本到 workspace）。 */
export const createProject = (name: string, source_folder: string) =>
  post<ProjectView>("/projects", { name, source_folder });

/** 项目列表（含状态）。 */
export const listProjects = () => get<ProjectView[]>("/projects");

/** 项目详情（项目 + 各组摘要）。 */
export const getProject = (id: number) => get<ProjectDetail>(`/projects/${id}`);

/** 删除项目：清理 workspace 副本 + 数据库资源。 */
export const deleteProject = (id: number) => del<null>(`/projects/${id}`);

/** 对项目跑分组并持久化（需模型就绪）。 */
export const groupProject = (id: number) =>
  post<ProjectDetail>(`/projects/${id}/group`, {});

/** 组详情（照片 + 评分 + 去留 + PK 进度）。 */
export const getGroup = (id: number, gk: string) =>
  get<GroupDetail>(`/projects/${id}/groups/${enc(gk)}`);

/** 对一组跑层①+层②评测并持久化（需就绪；层②可能 502）。 */
export const assessProjectGroup = (id: number, gk: string) =>
  post<GroupDetail>(`/projects/${id}/groups/${enc(gk)}/assess`, {});

/** 重试评测失败图（photoId 省略=该组全部未解决失败）。 */
export const retryGroup = (id: number, gk: string, photoId?: number) =>
  post<GroupDetail>(`/projects/${id}/groups/${enc(gk)}/retry`, { photo_id: photoId ?? null });

/** 忽略评测失败（解除阻塞；photoId 省略=全部）。 */
export const ignoreFailures = (id: number, gk: string, photoId?: number) =>
  post<GroupDetail>(`/projects/${id}/groups/${enc(gk)}/ignore-failures`, { photo_id: photoId ?? null });

/** 批量更新组内照片去留 / 救回标记。 */
export const updateSelection = (id: number, gk: string, changes: SelectionChange[]) =>
  post<GroupDetail>(`/projects/${id}/groups/${enc(gk)}/selection`, { changes });

/** 确认本组（标识，可反复改回）。 */
export const confirmGroup = (id: number, gk: string) =>
  post<GroupDetail>(`/projects/${id}/groups/${enc(gk)}/confirm`, {});

/** 一键通过：未评测的组先评测，再全部置为已确认。 */
export const confirmAll = (id: number) =>
  post<ProjectDetail>(`/projects/${id}/confirm-all`, {});

/** 完成：复制「通过」到目标目录 → 删 workspace → 标记完成。 */
export const completeProject = (id: number) =>
  post<CompleteResult>(`/projects/${id}/complete`, {});

/** 开始/恢复 PK。 */
export const pkStart = (id: number, gk: string, pool: string[], restart = false) =>
  post<PkView>(`/projects/${id}/groups/${enc(gk)}/pk/start`, { pool, restart });

/** 对当前一对落一次选择。 */
export const pkChoose = (id: number, gk: string, outcome: PkOutcome) =>
  post<PkView>(`/projects/${id}/groups/${enc(gk)}/pk/choose`, { outcome });

/** 撤销上一步 PK。 */
export const pkUndo = (id: number, gk: string) =>
  post<PkView>(`/projects/${id}/groups/${enc(gk)}/pk/undo`, {});
