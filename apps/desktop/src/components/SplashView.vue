<script setup lang="ts">
// 启动首屏：后端加载本地模型期间显示进度。
//  - 首次启动（需联网下载模型）→ 先弹窗告知预估体量，用户同意才开下、不同意则退出。
//  - 普通加载完成 → 短暂展示「就位」后自动进入应用。
//  - 首次下载完成 → 出现按钮，由用户点击进入。
//  - 下载失败 → 可重试；依赖缺失（致命）→ 不可重试，提示修复。
import { invoke } from "@tauri-apps/api/core";
import { computed, onUnmounted, ref, watch } from "vue";
import { useEngineStore } from "../stores/engine";

const engine = useEngineStore();
const emit = defineEmits<{ enter: [] }>();

type View = "connecting" | "offline" | "consent" | "loading" | "ready" | "retry" | "fatal";

// 用户一旦同意就不再回到确认弹窗（避免同意瞬间仍有在途轮询拿到 awaiting_consent 而回闪）
const consented = ref(false);

const view = computed<View>(() => {
  if (engine.phase === "offline") return "offline";
  if (engine.phase === "connecting" && !engine.health) return "connecting";
  const s = engine.health?.status;
  if (s === "ready") return "ready";
  if (s === "error") return engine.canRetry ? "retry" : "fatal";
  if (s === "awaiting_consent" && !consented.value) return "consent";
  return "loading";
});

const expectedGb = computed(() => ((engine.health?.expected_total_mb ?? 0) / 1024).toFixed(1));

function onConsent() {
  consented.value = true;
  void engine.consent();
}
function onDecline() {
  // 不同意首次下载 → 退出应用（无模型无法工作）
  void invoke("exit_app");
}

const progress = computed(
  () => engine.health?.progress ?? { current: 0, total: 0, step: "", downloaded_mb: 0, speed_mbps: 0, percent: 0 },
);
// 有实际下载流量时（首次/缺权重）才显示速度与字节，进度用字节百分比；否则用模块步骤进度
const hasDownload = computed(() => progress.value.speed_mbps > 0 || progress.value.downloaded_mb > 0);
const pct = computed(() => {
  const p = progress.value;
  if (hasDownload.value || engine.firstRun) return p.percent;
  return p.total ? Math.round((p.current / p.total) * 100) : 0;
});
const version = computed(() => engine.health?.version ?? "");

// 普通加载（非首次）完成后自动进入；首次下载完成则等用户点按钮。
const autoEntering = ref(false);
let enterTimer: number | undefined;
watch(
  () => engine.ready,
  (ready) => {
    if (ready && !engine.firstRun) {
      autoEntering.value = true;
      enterTimer = window.setTimeout(() => emit("enter"), 1600);
    }
  },
  { immediate: true },
);
onUnmounted(() => window.clearTimeout(enterTimer));
</script>

<template>
  <div class="splash">
    <div class="frame">
      <span class="corner tl" /><span class="corner tr" />
      <span class="corner bl" /><span class="corner br" />

      <div class="brand">
        <h1>Keeper</h1>
        <div class="sub">
          <span class="cn">留影</span>
          <span class="rule" />
          <span class="tag">把最好的留下，只留在你自己的电脑里</span>
        </div>
      </div>

      <Transition name="fade" mode="out-in">
        <!-- 连接中 -->
        <div v-if="view === 'connecting'" key="connecting" class="stage">
          <div class="aperture spinning" />
          <p class="line">正在连接推理服务…</p>
        </div>

        <!-- 服务未启动 -->
        <div v-else-if="view === 'offline'" key="offline" class="stage">
          <p class="line warn">本地推理服务尚未就绪</p>
          <p class="hint">正在启动内置推理服务，请稍候；若长时间无响应，请重启应用。<br />（开发模式下请在终端运行 <code>mise run sidecar</code>）</p>
          <button class="btn" @click="engine.refresh()">重新连接</button>
        </div>

        <!-- 首次下载确认 -->
        <div v-else-if="view === 'consent'" key="consent" class="stage">
          <p class="banner">
            首次启动 · 需要为你下载本地 AI 模型<em>仅此一次，下载后完全离线运行，照片不出本地</em>
          </p>
          <div class="consent-size">
            <span class="num">约 {{ expectedGb }} GB</span>
            <span class="unit">预估下载体量</span>
          </div>
          <p class="hint">模型保存在 <code>~/.keeper/models</code>，请确保网络通畅与磁盘空间充足。</p>
          <div class="consent-actions">
            <button class="btn" @click="onDecline">不同意 · 退出</button>
            <button class="btn btn--primary" @click="onConsent">同意并开始下载</button>
          </div>
        </div>

        <!-- 加载 / 下载中 -->
        <div v-else-if="view === 'loading'" key="loading" class="stage">
          <p v-if="engine.needsRepair" class="line warn">模型需要重新加载…</p>
          <p v-else-if="engine.firstRun" class="banner">
            首次启动 · 正在为你下载本地 AI 模型<em>仅此一次，之后完全离线运行</em>
          </p>
          <p v-else class="line">正在载入本地模型…</p>

          <div class="meter">
            <div class="track"><div class="fill" :style="{ width: pct + '%' }" /></div>
            <div class="meta">
              <span class="step">{{ progress.step ? "正在加载 " + progress.step : "准备中" }} · {{ progress.current }}/{{ progress.total || "·" }}</span>
              <span class="count">{{ pct }}%</span>
            </div>
            <div v-if="hasDownload" class="dl">已下载 {{ progress.downloaded_mb }} MB · {{ progress.speed_mbps }} MB/s</div>
          </div>
        </div>

        <!-- 就绪 -->
        <div v-else-if="view === 'ready'" key="ready" class="stage">
          <div class="aperture done" />
          <p class="line ok">本地模型已就位 · 暗房已备好</p>
          <p v-if="autoEntering" class="hint">正在进入…</p>
          <button v-else class="btn btn--primary" @click="emit('enter')">开始选片 →</button>
        </div>

        <!-- 可重试错误（下载失败等） -->
        <div v-else-if="view === 'retry'" key="retry" class="stage">
          <p class="line warn">模型加载未完成</p>
          <p class="hint err">{{ engine.health?.detail }}</p>
          <button class="btn btn--primary" @click="engine.retry()">重试下载</button>
        </div>

        <!-- 致命错误（依赖缺失，不可重试） -->
        <div v-else key="fatal" class="stage">
          <p class="line warn">无法启动 · 运行依赖缺失</p>
          <p class="hint err">{{ engine.health?.detail }}</p>
          <p class="hint">这台机器缺少运行所需的依赖，重试无法解决；请修复依赖安装后重启服务。</p>
        </div>
      </Transition>
    </div>

    <footer v-if="version" class="ver">KEEPER ENGINE · v{{ version }}</footer>
  </div>
</template>

<style scoped>
.splash {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 26px;
  padding: 40px;
}

/* 取景器框 */
.frame {
  position: relative;
  width: min(560px, 90vw);
  padding: 56px 56px 52px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 34px;
}
.corner {
  position: absolute;
  width: 26px;
  height: 26px;
  border: 2px solid var(--line-strong);
  opacity: 0;
  animation: corner-in 0.7s ease forwards;
}
.corner.tl { top: 0; left: 0; border-right: 0; border-bottom: 0; }
.corner.tr { top: 0; right: 0; border-left: 0; border-bottom: 0; animation-delay: 0.06s; }
.corner.bl { bottom: 0; left: 0; border-right: 0; border-top: 0; animation-delay: 0.12s; }
.corner.br { bottom: 0; right: 0; border-left: 0; border-top: 0; animation-delay: 0.18s; }
@keyframes corner-in {
  from { opacity: 0; transform: scale(1.25); }
  to { opacity: 1; transform: scale(1); }
}

/* 品牌 */
.brand {
  text-align: center;
  animation: rise 0.8s cubic-bezier(0.2, 0.8, 0.2, 1) both;
  animation-delay: 0.15s;
}
.brand h1 {
  margin: 0;
  font-family: var(--font-display);
  font-weight: 360;
  font-size: 76px;
  line-height: 0.92;
  letter-spacing: 0.01em;
  color: var(--ink);
  font-optical-sizing: auto;
}
.sub {
  margin-top: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}
.sub .cn {
  font-family: var(--font-display);
  font-size: 18px;
  color: var(--amber-bright);
  letter-spacing: 0.3em;
  padding-left: 0.3em;
}
.sub .rule { width: 28px; height: 1px; background: var(--line-strong); }
.sub .tag { color: var(--ink-faint); font-size: 12.5px; letter-spacing: 0.02em; }

/* 状态舞台 */
.stage {
  min-height: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  width: 100%;
  animation: rise 0.8s cubic-bezier(0.2, 0.8, 0.2, 1) both;
  animation-delay: 0.3s;
}
.line { margin: 0; font-size: 15px; color: var(--ink-dim); }
.line.ok { color: var(--green); font-weight: 500; }
.line.warn { color: var(--amber-bright); font-weight: 500; }
.hint { margin: 0; font-size: 12.5px; color: var(--ink-faint); text-align: center; max-width: 380px; line-height: 1.6; }
.hint.err { color: var(--red); font-family: var(--font-mono); font-size: 12px; word-break: break-word; }
.hint code {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--amber-bright);
  background: var(--amber-soft);
  padding: 2px 7px;
  border-radius: 5px;
}

.banner {
  margin: 0;
  text-align: center;
  font-size: 13.5px;
  color: var(--ink-dim);
  line-height: 1.7;
}
.banner em {
  display: block;
  margin-top: 3px;
  font-style: normal;
  font-size: 12px;
  color: var(--ink-faint);
}

/* 首次下载确认 */
.consent-size {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  margin: 2px 0;
}
.consent-size .num {
  font-family: var(--font-display);
  font-size: 34px;
  font-weight: 400;
  color: var(--amber-bright);
  letter-spacing: 0.01em;
}
.consent-size .unit {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-faint);
}
.consent-actions {
  display: flex;
  gap: 12px;
  margin-top: 6px;
}

/* 进度计 */
.meter { width: 100%; max-width: 400px; display: flex; flex-direction: column; gap: 10px; }
.track {
  position: relative;
  height: 6px;
  border-radius: 99px;
  background: var(--surface-2);
  overflow: hidden;
  /* 胶片刻度 */
  background-image: repeating-linear-gradient(
    90deg,
    transparent 0,
    transparent 13px,
    rgba(0, 0, 0, 0.35) 13px,
    rgba(0, 0, 0, 0.35) 14px
  );
}
.fill {
  height: 100%;
  border-radius: 99px;
  background: linear-gradient(90deg, var(--amber), var(--amber-bright));
  box-shadow: 0 0 14px rgba(245, 187, 82, 0.55);
  transition: width 0.5s cubic-bezier(0.3, 0.8, 0.3, 1);
  animation: glow 1.8s ease-in-out infinite;
}
@keyframes glow {
  50% { box-shadow: 0 0 22px rgba(245, 187, 82, 0.8); }
}
.meta {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-family: var(--font-mono);
  font-size: 12px;
}
.meta .step { color: var(--ink-dim); }
.meta .count { color: var(--amber); letter-spacing: 0.04em; }
.dl {
  margin-top: 2px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--ink-faint);
  letter-spacing: 0.03em;
}

/* 光圈装饰 */
.aperture {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 2px solid var(--line-strong);
  position: relative;
}
.aperture::after {
  content: "";
  position: absolute;
  inset: 6px;
  border-radius: 50%;
  border: 2px solid var(--amber);
}
.aperture.spinning::after {
  border-color: var(--amber) transparent var(--amber) transparent;
  animation: spin 1s linear infinite;
}
.aperture.done {
  border-color: var(--green);
}
.aperture.done::after {
  border-color: var(--green);
  inset: 6px;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

.ver {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.18em;
  color: var(--ink-faint);
  opacity: 0;
  animation: rise 1s ease both;
  animation-delay: 0.5s;
}

@keyframes rise {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.fade-enter-active,
.fade-leave-active { transition: opacity 0.3s ease, transform 0.3s ease; }
.fade-enter-from { opacity: 0; transform: translateY(8px); }
.fade-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
