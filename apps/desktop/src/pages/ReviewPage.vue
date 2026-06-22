<script setup lang="ts">
// 二次预览页：上区 kept、下区 discarded（跨组拍平）。复选框批量移动 + 卡片单击移动 +
// 一键勾选 kept 区杂图并置顶 + 点缩略图看大图。确认后进入 complete 页生成结果。
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useProjectsStore } from "../stores/projects";
import { thumbnailUrl, type PhotoView } from "../api";

const route = useRoute();
const router = useRouter();
const store = useProjectsStore();
const pid = computed(() => Number(route.params.id));

// 勾选集合（仅用于批量按钮）；junkFirst 控制 kept 区是否把杂图置顶
const checked = ref<Set<number>>(new Set());
const junkFirst = ref(false);

onMounted(() => store.loadReview(pid.value));

const kept = computed<PhotoView[]>(() => {
  const list = store.review?.kept ?? [];
  if (!junkFirst.value) return list;
  // 杂图置顶：稳定排序，is_junk 在前
  return [...list].sort((a, b) => Number(b.llm_is_junk) - Number(a.llm_is_junk));
});
const discarded = computed<PhotoView[]>(() => store.review?.discarded ?? []);

function toggleCheck(id: number) {
  const s = new Set(checked.value);
  s.has(id) ? s.delete(id) : s.add(id);
  checked.value = s;
}

function checkedIn(list: PhotoView[]): number[] {
  return list.filter((p) => checked.value.has(p.id)).map((p) => p.id);
}

async function move(ids: number[], selection: "KEPT" | "DISCARDED") {
  if (!ids.length) return;
  await store.reviewSelect(pid.value, ids, selection);
  checked.value = new Set();
  junkFirst.value = false;
}

// 单击卡片：把该张移到对侧区
const moveOne = (p: PhotoView) =>
  move([p.id], p.selection === "KEPT" ? "DISCARDED" : "KEPT");

// 一键勾选 kept 区杂图 + 置顶
function pickJunk() {
  const junkIds = (store.review?.kept ?? []).filter((p) => p.llm_is_junk).map((p) => p.id);
  checked.value = new Set(junkIds);
  junkFirst.value = true;
}

// 大图浮层
const preview = ref<PhotoView | null>(null);

async function doComplete() {
  await store.complete(pid.value);
  router.push(`/projects/${pid.value}/complete`);
}
</script>

<template>
  <section class="review">
    <RouterLink :to="`/projects/${pid}`" class="back">← 返回分组</RouterLink>
    <header class="rhead">
      <h1>最终预览</h1>
      <p class="muted">上方为<strong>保留</strong>，下方为<strong>放弃</strong>。可二次调整后生成。</p>
    </header>

    <p v-if="store.busy" class="muted">处理中…</p>
    <p v-if="store.error" class="err">{{ store.error }}</p>

    <section class="zone">
      <div class="zone-bar">
        <h2>保留 · {{ kept.length }}</h2>
        <button class="btn" :disabled="store.busy" @click="pickJunk">一键勾选杂图</button>
        <button class="btn btn--danger" :disabled="store.busy || !checkedIn(kept).length"
                @click="move(checkedIn(kept), 'DISCARDED')">
          移至放弃区（{{ checkedIn(kept).length }}）
        </button>
      </div>
      <ul class="grid">
        <li v-for="p in kept" :key="p.id" class="card" :class="{ on: checked.has(p.id) }">
          <input type="checkbox" :checked="checked.has(p.id)" @change="toggleCheck(p.id)" />
          <span v-if="p.llm_is_junk" class="badge">杂图</span>
          <img :src="thumbnailUrl(p.workspace_path)" :alt="p.filename" @click="preview = p" />
          <div class="cap">
            <span>{{ p.group_key }} · {{ p.llm_score?.toFixed(0) ?? "-" }}</span>
            <button class="mini" @click="moveOne(p)">放弃</button>
          </div>
        </li>
      </ul>
    </section>

    <section class="zone zone--out">
      <div class="zone-bar">
        <h2>放弃 · {{ discarded.length }}</h2>
        <button class="btn" :disabled="store.busy || !checkedIn(discarded).length"
                @click="move(checkedIn(discarded), 'KEPT')">
          移至保留区（{{ checkedIn(discarded).length }}）
        </button>
      </div>
      <ul class="grid">
        <li v-for="p in discarded" :key="p.id" class="card" :class="{ on: checked.has(p.id) }">
          <input type="checkbox" :checked="checked.has(p.id)" @change="toggleCheck(p.id)" />
          <span v-if="p.llm_is_junk" class="badge">杂图</span>
          <img :src="thumbnailUrl(p.workspace_path)" :alt="p.filename" @click="preview = p" />
          <div class="cap">
            <span>{{ p.group_key }} · {{ p.llm_score?.toFixed(0) ?? "-" }}</span>
            <button class="mini" @click="moveOne(p)">保留</button>
          </div>
        </li>
      </ul>
    </section>

    <footer class="actions">
      <span class="grow" />
      <button class="btn btn--keep" :disabled="store.busy" @click="doComplete">确认并生成</button>
    </footer>

    <div v-if="preview" class="lightbox" @click="preview = null">
      <img :src="thumbnailUrl(preview.workspace_path, 1024)" :alt="preview.filename" />
      <div class="lb-meta">
        <strong>{{ preview.filename }}</strong>
        <span>分 {{ preview.llm_score?.toFixed(0) ?? "-" }}</span>
        <span v-if="preview.llm_is_junk" class="badge">杂图</span>
        <span v-if="preview.llm_flaws">缺陷：{{ preview.llm_flaws }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.review { display: flex; flex-direction: column; gap: 16px; }
.back { color: var(--ink-dim); text-decoration: none; font-size: 13px; width: fit-content; }
.back:hover { color: var(--amber-bright); }
.rhead h1 { margin: 0 0 4px; font-family: var(--font-display); font-weight: 400; font-size: 26px; }
.muted { color: var(--ink-faint); font-size: 13px; margin: 0; }
.err { color: #e06c6c; font-size: 13px; }
.zone { display: flex; flex-direction: column; gap: 10px; }
.zone--out { opacity: 0.85; }
.zone-bar { display: flex; align-items: center; gap: 10px; }
.zone-bar h2 { margin: 0; font-size: 16px; font-weight: 500; flex: 1; }
.grid { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px;
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); }
.card { position: relative; border: 1px solid var(--line, #333); border-radius: 8px; overflow: hidden; }
.card.on { outline: 2px solid var(--amber-bright, #e0a040); }
.card input[type="checkbox"] { position: absolute; top: 6px; left: 6px; z-index: 2; }
.card .badge, .lb-meta .badge { background: #b4453a; color: #fff; font-size: 11px;
        padding: 1px 6px; border-radius: 4px; }
.card .badge { position: absolute; top: 6px; right: 6px; z-index: 2; }
.card img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; cursor: zoom-in; }
.cap { display: flex; align-items: center; justify-content: space-between; gap: 6px;
       padding: 4px 6px; font-size: 12px; font-family: var(--font-mono); color: var(--ink-faint); }
.mini { font-size: 11px; padding: 1px 6px; cursor: pointer; }
.actions { display: flex; align-items: center; gap: 10px; }
.grow { flex: 1; }
.btn { padding: 6px 14px; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.lightbox { position: fixed; inset: 0; background: rgba(0,0,0,0.85); z-index: 50;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            gap: 12px; cursor: zoom-out; }
.lightbox img { max-width: 90vw; max-height: 80vh; object-fit: contain; }
.lb-meta { display: flex; gap: 12px; align-items: center; color: #ddd; font-size: 13px; }
</style>
