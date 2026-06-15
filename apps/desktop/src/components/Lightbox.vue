<script setup lang="ts">
// 图片放大预览：全屏遮罩 + 大图，支持左右切换（多图）/ Esc 关闭。
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { thumbnailUrl } from "../api";
import { basename } from "../util/format";

const props = defineProps<{ paths: string[]; labels?: string[]; start?: number }>();
const emit = defineEmits<{ close: [] }>();

const idx = ref(props.start ?? 0);
watch(() => props.start, (v) => (idx.value = v ?? 0));

const current = computed(() => props.paths[idx.value]);
// 优先展示带路径的原始文件名（labels），无则退回 workspace 文件名
const caption = computed(() => props.labels?.[idx.value] ?? basename(current.value));
const multi = computed(() => props.paths.length > 1);

function prev() {
  idx.value = (idx.value - 1 + props.paths.length) % props.paths.length;
}
function next() {
  idx.value = (idx.value + 1) % props.paths.length;
}
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
  else if (e.key === "ArrowLeft") prev();
  else if (e.key === "ArrowRight") next();
}

onMounted(() => window.addEventListener("keydown", onKey));
onUnmounted(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <Teleport to="body">
    <div class="lb" @click.self="emit('close')" @click.stop>
      <button class="x" @click.stop="emit('close')">关闭 <kbd>Esc</kbd></button>

      <button v-if="multi" class="nav prev" @click.stop="prev" aria-label="上一张">‹</button>
      <figure class="stage" @click.self="emit('close')">
        <img :key="current" :src="thumbnailUrl(current, 1600)" alt="" />
        <figcaption>
          <span class="name">{{ caption }}</span>
          <span v-if="multi" class="of">{{ idx + 1 }} / {{ paths.length }}</span>
        </figcaption>
      </figure>
      <button v-if="multi" class="nav next" @click.stop="next" aria-label="下一张">›</button>
    </div>
  </Teleport>
</template>

<style scoped>
.lb {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 56px 64px;
  background: rgba(10, 8, 4, 0.86);
  backdrop-filter: blur(6px);
  animation: fade 0.16s ease;
}
@keyframes fade {
  from { opacity: 0; }
  to { opacity: 1; }
}
.x {
  position: absolute;
  top: 18px;
  right: 22px;
  font-family: var(--font-body);
  font-size: 13px;
  color: var(--ink-dim);
  background: transparent;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  padding: 7px 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  transition: color 0.18s, border-color 0.18s;
}
.x:hover { color: var(--amber-bright); border-color: var(--amber); }
.stage {
  margin: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  min-width: 0;
  max-width: 100%;
  max-height: 100%;
}
.stage img {
  max-width: 100%;
  max-height: calc(100vh - 130px);
  object-fit: contain;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow);
  background: var(--surface);
  animation: pop 0.18s ease;
}
@keyframes pop {
  from { opacity: 0; transform: scale(0.985); }
  to { opacity: 1; transform: scale(1); }
}
.stage figcaption {
  display: flex;
  align-items: center;
  gap: 14px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-dim);
}
.of { color: var(--ink-faint); }
.nav {
  flex: none;
  width: 46px;
  height: 46px;
  font-size: 28px;
  line-height: 1;
  color: var(--ink-dim);
  background: rgba(34, 28, 19, 0.7);
  border: 1px solid var(--line-strong);
  border-radius: 50%;
  cursor: pointer;
  transition: color 0.18s, border-color 0.18s, background 0.18s;
}
.nav:hover { color: var(--amber-bright); border-color: var(--amber); background: var(--surface-2); }
kbd {
  font-family: var(--font-mono);
  font-size: 10.5px;
  padding: 1px 5px;
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  color: var(--ink-faint);
}
</style>
