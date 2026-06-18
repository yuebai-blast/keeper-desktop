<script setup lang="ts">
// PK 擂台：用户两两对决，四种结局（选左/选右/都选/都不选）。
// 状态权威在 sidecar（每次选择持久化），本组件只驱动交互、显示当前一对。
import { computed, onMounted, onUnmounted, ref } from "vue";
import { thumbnailUrl, type PhotoView, type PkOutcome, type PkView } from "../api";
import { useProjectsStore } from "../stores/projects";
import PhotoStats from "./PhotoStats.vue";

const props = defineProps<{
  projectId: number;
  gk: string;
  pool: string[];
  restart: boolean;
  photos: PhotoView[];
}>();
const emit = defineEmits<{ close: [] }>();

const store = useProjectsStore();
const view = ref<PkView | null>(null);
const busy = ref(false);

const byPath = computed<Record<string, PhotoView>>(() =>
  Object.fromEntries(props.photos.map((p) => [p.workspace_path, p])),
);
const left = computed(() => (view.value?.current ? byPath.value[view.value.current[0]] : null));
const right = computed(() => (view.value?.current ? byPath.value[view.value.current[1]] : null));
const done = computed(() => view.value?.done ?? false);

async function choose(outcome: PkOutcome) {
  if (busy.value || done.value || !view.value?.current) return;
  busy.value = true;
  try {
    view.value = await store.pkChoose(props.projectId, props.gk, outcome);
  } finally {
    busy.value = false;
  }
}
async function undo() {
  if (busy.value || !view.value?.can_undo) return;
  busy.value = true;
  try {
    view.value = await store.pkUndo(props.projectId, props.gk);
  } finally {
    busy.value = false;
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") return emit("close");
  if (done.value) return;
  if (e.key === "ArrowLeft") choose("PICK_LEFT");
  else if (e.key === "ArrowRight") choose("PICK_RIGHT");
  else if (e.key === "ArrowUp") choose("KEEP_BOTH");
  else if (e.key === "ArrowDown") choose("DROP_BOTH");
  else if (e.key === "u" || e.key === "U") undo();
}

onMounted(async () => {
  busy.value = true;
  try {
    view.value = await store.pkStart(props.projectId, props.gk, props.pool, props.restart);
  } finally {
    busy.value = false;
  }
  window.addEventListener("keydown", onKey);
});
onUnmounted(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="arena">
    <div class="bar">
      <span class="title">PK 擂台</span>
      <span class="sep" />
      <span v-if="view && !done" class="round">剩 {{ view.pool_remaining }} 张待登场 · 已留 {{ view.kept_aside.length }}</span>
      <span v-else-if="done" class="round done">本组 PK 结束</span>
      <span class="grow" />
      <button class="btn btn--ghost" @click="emit('close')">退出 <kbd>Esc</kbd></button>
    </div>

    <!-- 对决中 -->
    <template v-if="view && !done && left && right">
      <div class="duel">
        <figure class="card" @click="choose('PICK_LEFT')">
          <img :src="thumbnailUrl(left.workspace_path, 1024)" alt="" />
          <figcaption>留左 <kbd>←</kbd></figcaption>
          <div class="info"><PhotoStats :photo="left" /></div>
        </figure>
        <div class="mid">
          <div class="vs"><span>VS</span></div>
          <button class="btn btn--keep" @click="choose('KEEP_BOTH')">都留 <kbd>↑</kbd></button>
          <button class="btn btn--danger" @click="choose('DROP_BOTH')">都弃 <kbd>↓</kbd></button>
        </div>
        <figure class="card" @click="choose('PICK_RIGHT')">
          <img :src="thumbnailUrl(right.workspace_path, 1024)" alt="" />
          <figcaption>留右 <kbd>→</kbd></figcaption>
          <div class="info"><PhotoStats :photo="right" /></div>
        </figure>
      </div>
      <footer>
        <button class="btn" :disabled="!view.can_undo" @click="undo">撤销 <kbd>U</kbd></button>
        <span class="grow" />
        <span class="muted">点图=留该张并继续守擂；都留=两张都通过；都弃=两张都淘汰</span>
      </footer>
    </template>

    <!-- 结束 -->
    <template v-else-if="done">
      <div class="result">
        <p class="big">PK 完成</p>
        <p class="muted">已为本组更新「通过 / 未通过」，回到组详情查看。</p>
        <button class="btn btn--keep lg" @click="emit('close')">完成 <kbd>↵</kbd></button>
      </div>
    </template>

    <div v-else class="result"><p class="muted">正在准备…</p></div>
  </div>
</template>

<style scoped>
.arena {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: radial-gradient(120% 90% at 50% 0%, rgba(28, 21, 12, 0.98), rgba(8, 6, 4, 0.99));
  display: flex;
  flex-direction: column;
  padding: 18px 22px 22px;
  gap: 16px;
}
.bar { display: flex; align-items: center; gap: 12px; }
.bar .title { font-family: var(--font-display); font-size: 16px; }
.bar .sep { width: 1px; height: 16px; background: var(--line-strong); }
.round { font-family: var(--font-mono); font-size: 12.5px; color: var(--amber); letter-spacing: 0.04em; }
.round.done { color: var(--green); }
.grow { flex: 1; }

.duel { flex: 1; display: flex; align-items: stretch; justify-content: center; gap: 20px; min-height: 0; }
.card {
  margin: 0;
  position: relative;
  flex: 1;
  max-width: 42%;
  display: flex;
  flex-direction: column;
  cursor: pointer;
  border-radius: 12px;
  border: 2px solid var(--line);
  background: rgba(0, 0, 0, 0.25);
  transition: border-color 0.16s, box-shadow 0.2s;
  overflow: hidden;
}
.card:hover { border-color: var(--amber); box-shadow: 0 0 0 4px var(--amber-soft), var(--shadow); }
.card img { width: 100%; flex: 1; min-height: 0; object-fit: contain; display: block; background: #000; }
.card figcaption {
  position: absolute; top: 12px; left: 12px;
  font-size: 12px; color: var(--ink); background: rgba(0, 0, 0, 0.55);
  padding: 4px 10px; border-radius: 7px; display: inline-flex; gap: 7px; align-items: center;
  backdrop-filter: blur(3px);
}
.card .info {
  background: rgba(0, 0, 0, 0.4);
  border-top: 1px solid var(--line);
  padding: 12px 14px;
  max-height: 38%;
  overflow: auto;
}
.mid { flex: none; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; }
.vs { width: 50px; height: 50px; border-radius: 50%; border: 1px solid var(--line-strong); display: grid; place-items: center; }
.vs span { font-family: var(--font-display); font-style: italic; font-size: 17px; color: var(--amber); }

footer { display: flex; align-items: center; gap: 12px; }
.muted { color: var(--ink-faint); font-size: 12px; font-family: var(--font-mono); }

.result { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; }
.result .big { font-family: var(--font-display); font-size: 26px; color: var(--green); margin: 0; }
.result .lg { padding: 11px 24px; font-size: 14.5px; }

kbd {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink);
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid var(--line-strong);
  border-radius: 5px;
  padding: 1px 6px;
  min-width: 18px;
  text-align: center;
}
.btn--keep kbd, .btn--danger kbd { color: inherit; border-color: currentColor; opacity: 0.7; }
</style>
