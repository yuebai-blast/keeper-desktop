// 进度展示文案：阶段中文名 + 照片级「阶段 X / N」；评测（层①/层②）与分组（EMBED/CLUSTER）复用。
import { AssessPhase, type AssessProgress } from "../api";

const PHASE_LABEL: Record<string, string> = {
  [AssessPhase.LAYER1]: "本地评分",
  [AssessPhase.LAYER2]: "大模型打分",
  [AssessPhase.EMBED]: "分组",
};

/** 阶段中文名（IDLE/DONE/CLUSTER 无计数文案）。 */
export function phaseLabel(phase: string): string {
  return PHASE_LABEL[phase] ?? "";
}

/** 照片级进度文本，如「分组 12 / 300」；聚类阶段为不确定态文案；非计数阶段返回准备中。 */
export function photoProgressText(p: AssessProgress): string {
  if (p.phase === AssessPhase.CLUSTER) return "正在归类…";
  const label = phaseLabel(p.phase);
  if (!label) return "准备中…";
  return `${label} ${p.done} / ${p.total}`;
}
