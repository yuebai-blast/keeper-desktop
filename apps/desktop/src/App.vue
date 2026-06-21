<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import SplashView from "./components/SplashView.vue";
import UpdateBanner from "./components/UpdateBanner.vue";
import { useEngineStore } from "./stores/engine";
import { useUpdaterStore } from "./stores/updater";

const engine = useEngineStore();
const updater = useUpdaterStore();

// 用户是否已穿过加载页进入应用（加载页 ready 后自动/点按钮置位）
const entered = ref(false);

let timer: number | undefined;
// 终态：就绪、或不可重试的致命错误后停止轮询；其余（连不上/加载中/可重试）持续刷新
const settled = computed(
  () =>
    engine.phase === "online" &&
    (engine.health?.status === "ready" ||
      (engine.health?.status === "error" && engine.health?.retryable === false)),
);
function stopPoll() {
  if (timer) window.clearInterval(timer);
  timer = undefined;
}
function startPoll() {
  stopPoll();
  timer = window.setInterval(async () => {
    if (settled.value) return stopPoll();
    await engine.refresh();
  }, 800);
}

// 穿过加载页进入应用；修复完成（重新加载页 emit enter）时一并清掉修复标记
function onEnter() {
  entered.value = true;
  engine.clearRepair();
}
// 运行时触发修复（needsRepair）→ 重新加载已转 loading，重启轮询刷新进度
watch(
  () => engine.needsRepair,
  (v) => {
    if (v) startPoll();
  },
);

onMounted(async () => {
  await engine.refresh();
  startPoll();
  // 启动静默检查更新：失败/无更新都不打扰用户（仅有新版才弹横幅）。不 await，不阻塞主流程。
  void updater.check(true);
});
onUnmounted(stopPoll);
</script>

<template>
  <SplashView v-if="!entered || engine.needsRepair" @enter="onEnter" />

  <div v-else class="shell">
    <header class="topbar">
      <RouterLink to="/" class="wordmark">
        <span class="k">Keeper</span>
        <span class="cn">留影</span>
      </RouterLink>
      <span class="grow" />
      <span class="ready"><i /> 就绪</span>
    </header>
    <UpdateBanner />
    <RouterView />
  </div>
</template>

<style scoped>
.shell {
  /* 流式铺开：随窗口宽度自适应，2200px 安全上限仅为防极端高分屏过度拉伸
     （标准 24/27/32 寸笔记本/显示器用不到此上限；带鱼屏不在适配范围）。
     横向留白随窗口在 24~56px 间缩放。 */
  width: 100%;
  max-width: 2200px;
  margin: 0 auto;
  padding: 0 clamp(24px, 3.5vw, 56px) 80px;
}
.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px 0 16px;
  margin-bottom: 8px;
  background: linear-gradient(var(--bg) 72%, transparent);
  backdrop-filter: blur(2px);
}
.wordmark {
  display: flex;
  align-items: baseline;
  gap: 9px;
  text-decoration: none;
  color: inherit;
}
.wordmark .k {
  font-family: var(--font-display);
  font-weight: 400;
  font-size: 23px;
  letter-spacing: 0.01em;
}
.wordmark .cn {
  font-family: var(--font-display);
  font-size: 13px;
  color: var(--amber);
  letter-spacing: 0.28em;
  padding-left: 0.28em;
}
.grow {
  flex: 1;
}
.ready {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ink-faint);
  font-family: var(--font-mono);
  letter-spacing: 0.05em;
}
.ready i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 8px var(--green);
}
</style>
