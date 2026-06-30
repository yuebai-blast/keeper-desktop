<script setup lang="ts">
// 组内照片缩略图条：默认只展示一行，超过一行给出「展开 / 收起」按钮；
// 每张图悬停露出放大按钮，点击打开 Lightbox 预览（自带左右切换）。
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { thumbnailUrl } from "../api";
import Lightbox from "./Lightbox.vue";

const props = withDefaults(
  defineProps<{
    paths: string[];
    labels?: string[];
    ids?: number[]; // 与 paths 平行：各缩略图的 photo_id（拖拽移组用）
    sourceGroupKey?: string; // 这些缩略图所属组的 key
    canDrag?: boolean; // 是否允许从本组拖出（已确认/已处理组传 false 锁定）
  }>(),
  { canDrag: false },
);

// 开始拖拽：把 photoId + 源组 key 写入 dataTransfer，供目标卡片放置时读取。
function onDragStart(i: number, e: DragEvent) {
  if (!props.canDrag || !props.ids || !e.dataTransfer) return;
  e.dataTransfer.setData(
    "application/x-keeper-photo",
    JSON.stringify({ photoId: props.ids[i], sourceGroupKey: props.sourceGroupKey }),
  );
  e.dataTransfer.effectAllowed = "move";
}

const THUMB_H = 84; // 单行缩略图高度（px），同步 .strip max-height / .thumb height

const strip = ref<HTMLElement | null>(null);
const expanded = ref(false);
const overflowing = ref(false); // 内容是否超过一行（决定是否显示展开按钮）

const lightboxAt = ref<number | null>(null); // 非空时打开预览，值为起始索引

function measure() {
  const el = strip.value;
  if (!el) return;
  // scrollHeight 反映全部内容高度；超过一行高度即说明会换行。
  overflowing.value = el.scrollHeight > THUMB_H + 6;
}

function toggle(e: MouseEvent) {
  e.stopPropagation();
  expanded.value = !expanded.value;
}

function zoom(i: number, e: MouseEvent) {
  e.stopPropagation();
  lightboxAt.value = i;
}

let ro: ResizeObserver | null = null;
onMounted(() => {
  ro = new ResizeObserver(() => measure());
  if (strip.value) ro.observe(strip.value);
  nextTick(measure);
});
onBeforeUnmount(() => ro?.disconnect());
watch(() => props.paths, () => nextTick(measure));
</script>

<template>
  <!-- 容器不拦截冒泡：缩略图/展开按钮各自 stop，留白处的点击仍冒泡到卡片以进入分组详情 -->
  <div v-if="paths.length" class="thumbs">
    <div ref="strip" class="strip" :class="{ collapsed: !expanded }">
      <figure
        v-for="(p, i) in paths"
        :key="p"
        class="thumb"
        :draggable="canDrag"
        @dragstart="onDragStart(i, $event)"
        @click="zoom(i, $event)"
      >
        <img :src="thumbnailUrl(p, 256)" loading="lazy" alt="" />
        <button class="zoom" title="放大预览" @click.stop="zoom(i, $event)">⤢</button>
      </figure>
    </div>

    <button v-if="overflowing" class="toggle" @click="toggle">
      {{ expanded ? "收起" : `展开全部 ${paths.length} 张` }}
      <span class="chev" :class="{ up: expanded }">⌄</span>
    </button>
  </div>

  <Lightbox
    v-if="lightboxAt !== null"
    :paths="paths"
    :labels="labels"
    :start="lightboxAt"
    @close="lightboxAt = null"
  />
</template>

<style scoped>
.thumbs { margin-top: 11px; display: flex; flex-direction: column; gap: 8px; }
.strip {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  overflow: hidden;
  transition: max-height 0.22s ease;
}
.strip.collapsed { max-height: 84px; } /* = THUMB_H，仅露出一行 */
.thumb {
  position: relative;
  margin: 0;
  height: 84px; /* 统一高度、宽度随图自适应——保留每张照片的真实比例，不裁切变形 */
  flex: none;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--surface-2);
  cursor: zoom-in;
}
.thumb img {
  height: 100%;
  width: auto;
  max-width: 220px; /* 极端宽幅图兜底，避免单张过宽 */
  object-fit: cover;
  display: block;
  transition: transform 0.2s ease, filter 0.2s ease;
}
.thumb:hover img { transform: scale(1.05); filter: brightness(0.7); }
.zoom {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) scale(0.85);
  width: 30px;
  height: 30px;
  font-size: 16px;
  line-height: 1;
  color: var(--ink);
  background: rgba(20, 16, 10, 0.7);
  border: 1px solid var(--line-strong);
  border-radius: 50%;
  cursor: zoom-in;
  opacity: 0;
  transition: opacity 0.18s ease, transform 0.18s ease, border-color 0.18s;
}
.thumb:hover .zoom { opacity: 1; transform: translate(-50%, -50%) scale(1); }
.zoom:hover { border-color: var(--amber); color: var(--amber-bright); }
.toggle {
  align-self: flex-start;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--ink-dim);
  background: transparent;
  border: none;
  padding: 2px 0;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  transition: color 0.18s;
}
.toggle:hover { color: var(--amber-bright); }
.chev { transition: transform 0.2s ease; }
.chev.up { transform: rotate(180deg); }
</style>
