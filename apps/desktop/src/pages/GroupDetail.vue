<script setup lang="ts">
// 组详情：评测（层①+层②）→ 通过/未通过分区（按分排序，展示全部数据）→ 救回 + PK + 确认。
import { computed, onMounted, ref } from "vue";
import { thumbnailUrl, type PhotoView } from "../api";
import Arena from "../components/Arena.vue";
import PhotoStats from "../components/PhotoStats.vue";
import { useEngineStore } from "../stores/engine";
import { useProjectsStore } from "../stores/projects";
import { basename, byScoreDesc } from "../util/format";

const props = defineProps<{ id: string; gk: string }>();
const store = useProjectsStore();
const engine = useEngineStore();
const pid = computed(() => Number(props.id));

const arenaOpen = ref(false);
const arenaRestart = ref(true);

onMounted(() => store.loadGroup(pid.value, props.gk));

const group = computed(() => store.group);
const assessed = computed(() => group.value && group.value.group.status !== "PENDING");
const photos = computed<PhotoView[]>(() => group.value?.photos ?? []);
const passed = computed(() => photos.value.filter((p) => p.selection === "KEPT").sort(byScoreDesc));
const failed = computed(() => photos.value.filter((p) => p.selection === "DISCARDED").sort(byScoreDesc));
const pool = computed(() =>
  photos.value.filter((p) => p.selection === "KEPT" || p.rescued).map((p) => p.workspace_path),
);
const pkInProgress = computed(() => !!group.value?.pk && !group.value.pk.done);
const blocked = computed(() => (group.value?.group.failed_count ?? 0) > 0);
function retryOne(p: PhotoView) { store.retry(pid.value, props.gk, p.id); }
function ignoreOne(p: PhotoView) { store.ignoreFailures(pid.value, props.gk, p.id); }
function retryAll() { store.retry(pid.value, props.gk); }

async function assess() {
  await store.assess(pid.value, props.gk);
}
function startPk(restart: boolean) {
  arenaRestart.value = restart;
  arenaOpen.value = true;
}
async function onArenaClose() {
  arenaOpen.value = false;
  await store.loadGroup(pid.value, props.gk); // 刷新通过/未通过区域
}
function toKept(p: PhotoView) {
  store.toggleSelection(pid.value, props.gk, p.id, "KEPT");
}
function toDiscarded(p: PhotoView) {
  store.toggleSelection(pid.value, props.gk, p.id, "DISCARDED");
}
function rescue(p: PhotoView) {
  store.rescue(pid.value, props.gk, p.id, !p.rescued);
}
</script>

<template>
  <section v-if="group" class="gd">
    <RouterLink :to="`/projects/${pid}`" class="back">← 分组列表</RouterLink>
    <header class="ghead">
      <h1>组 · {{ group.group.group_key }}</h1>
      <p class="meta">
        <span>{{ group.group.photo_count }} 张</span>
        <span v-if="group.group.location">· {{ group.group.location }}</span>
        <span class="status" :class="`s-${group.group.status}`">
          {{ group.group.status === "CONFIRMED" ? "已确认" : assessed ? "已评测" : "待评测" }}
        </span>
      </p>
    </header>

    <p v-if="store.error" class="err">{{ store.error }}</p>

    <!-- 未评测：评测入口 -->
    <div v-if="!assessed" class="pre">
      <div class="thumbs">
        <img v-for="p in photos" :key="p.id" :src="thumbnailUrl(p.workspace_path)" loading="lazy" alt="" />
      </div>
      <button class="btn btn--primary lg" :disabled="store.busy || !engine.ready" @click="assess">
        {{ store.busy ? "评测中（本地 + 大模型）…" : "用模型评测本组" }}
      </button>
      <p class="hint">先本地打分筛选，再对入选的调用大模型打分，自动分出「通过 / 未通过」。</p>
    </div>

    <!-- 已评测：通过 / 未通过 -->
    <template v-else>
      <div class="toolbar">
        <button class="btn" :disabled="!pool.length || blocked" @click="startPk(true)">
          开始 PK（{{ pool.length }} 张）
        </button>
        <button v-if="pkInProgress" class="btn" :disabled="blocked" @click="startPk(false)">继续上次 PK</button>
        <button v-if="blocked" class="btn btn--ghost" :disabled="store.busy" @click="retryAll">
          重试全部失败（{{ group.group.failed_count }}）
        </button>
        <span class="grow" />
        <button class="btn btn--keep" :disabled="blocked" @click="store.confirmGroup(pid, gk)">
          {{ group.group.status === "CONFIRMED" ? "✓ 已确认（可再改）" : "确认本组" }}
        </button>
      </div>
      <p v-if="blocked" class="warn">还有 {{ group.group.failed_count }} 张未评测成功，请先重试或忽略后再裁决。</p>

      <h2 class="sect">通过 <small>{{ passed.length }}</small></h2>
      <p v-if="!passed.length" class="empty">暂无通过的照片。</p>
      <div class="cards">
        <article v-for="p in passed" :key="p.id" class="pcard kept">
          <figure>
            <img :src="thumbnailUrl(p.workspace_path, 512)" loading="lazy" alt="" />
            <figcaption>{{ basename(p.filename) }}</figcaption>
          </figure>
          <div class="body">
            <PhotoStats :photo="p" />
            <div class="ops">
              <button class="btn btn--ghost" :disabled="blocked" @click="toDiscarded(p)">移到未通过</button>
            </div>
          </div>
        </article>
      </div>

      <h2 class="sect">未通过 <small>{{ failed.length }}</small></h2>
      <p v-if="!failed.length" class="empty">没有被淘汰的照片。</p>
      <div class="cards">
        <article v-for="p in failed" :key="p.id" class="pcard out" :class="{ rescued: p.rescued, failed: !!p.assess_error }">
          <figure>
            <img :src="thumbnailUrl(p.workspace_path, 512)" loading="lazy" alt="" />
            <figcaption>{{ basename(p.filename) }}</figcaption>
            <span v-if="p.assess_error" class="etag">评测失败</span>
            <span v-else-if="p.rescued" class="rtag">已救回</span>
          </figure>
          <div class="body">
            <p v-if="p.assess_error" class="eerr" :title="p.assess_error">
              评测失败：{{ p.assess_error }}
            </p>
            <PhotoStats :photo="p" />
            <div class="ops">
              <template v-if="p.assess_error && !p.assess_error_ignored">
                <button class="btn btn--ghost" :disabled="store.busy" @click="retryOne(p)">重试</button>
                <button class="btn btn--ghost" :disabled="store.busy" @click="ignoreOne(p)">忽略</button>
              </template>
              <template v-else>
                <button class="btn btn--ghost" :disabled="blocked" @click="rescue(p)">{{ p.rescued ? "取消救回" : "救回进 PK" }}</button>
                <button class="btn btn--ghost" :disabled="blocked" @click="toKept(p)">直接设为通过</button>
              </template>
            </div>
          </div>
        </article>
      </div>
    </template>
  </section>

  <Arena
    v-if="arenaOpen && group"
    :project-id="pid"
    :gk="gk"
    :pool="pool"
    :restart="arenaRestart"
    :photos="photos"
    @close="onArenaClose"
  />
</template>

<style scoped>
.gd { display: flex; flex-direction: column; gap: 14px; }
.back { color: var(--ink-dim); text-decoration: none; font-size: 13px; width: fit-content; }
.back:hover { color: var(--amber-bright); }
.ghead h1 { margin: 0 0 4px; font-family: var(--font-display); font-weight: 400; font-size: 24px; }
.meta { margin: 0; display: flex; align-items: center; gap: 9px; color: var(--ink-faint); font-size: 12.5px; font-family: var(--font-mono); }
.status { padding: 2px 9px; border-radius: 20px; border: 1px solid var(--line-strong); color: var(--ink-dim); font-size: 11px; }
.status.s-CONFIRMED { color: var(--green); border-color: var(--green); }
.status.s-ASSESSED { color: var(--amber-bright); border-color: var(--amber); }
.err { color: var(--red); font-family: var(--font-mono); font-size: 13px; }

.pre { display: flex; flex-direction: column; gap: 16px; align-items: flex-start; }
.pre .thumbs { display: flex; flex-wrap: wrap; gap: 8px; }
.pre .thumbs img { width: 96px; height: 96px; object-fit: cover; border-radius: 8px; background: var(--surface-2); }
.btn.lg { padding: 12px 24px; font-size: 14.5px; }
.hint { margin: 0; color: var(--ink-faint); font-size: 12.5px; }

.toolbar { display: flex; align-items: center; gap: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
.grow { flex: 1; }

.sect { margin: 8px 0 2px; font-family: var(--font-display); font-weight: 400; font-size: 19px; }
.sect small { font-family: var(--font-mono); font-size: 13px; color: var(--ink-faint); margin-left: 6px; }
.empty { color: var(--ink-faint); font-size: 13px; margin: 0; }

/* 响应式网格：通过/未通过照片随窗口宽度多列排布（每列 ≥520px，容纳 200px 缩略图 + 信息） */
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(520px, 1fr)); gap: 12px; }
.pcard {
  display: flex;
  gap: 16px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 3px solid transparent;
  border-radius: var(--radius);
  padding: 14px 16px;
}
.pcard.kept { border-left-color: var(--green); }
.pcard.out { opacity: 0.92; }
.pcard.rescued { border-left-color: var(--amber); opacity: 1; }
.pcard.failed { border-left-color: var(--red); opacity: 1; }
.etag {
  position: absolute; top: 8px; left: 8px;
  font-family: var(--font-mono); font-size: 10.5px;
  color: #fff; background: var(--red);
  padding: 2px 8px; border-radius: 5px;
}
.eerr {
  margin: 0; color: var(--red); font-family: var(--font-mono); font-size: 12px;
  word-break: break-all;
}
.pcard figure { margin: 0; position: relative; flex: none; width: 200px; }
.pcard img { width: 200px; height: 150px; object-fit: cover; border-radius: 8px; background: var(--surface-2); display: block; }
.pcard figcaption { margin-top: 5px; font-size: 11px; color: var(--ink-faint); font-family: var(--font-mono); word-break: break-all; }
.rtag {
  position: absolute; top: 8px; left: 8px;
  font-family: var(--font-mono); font-size: 10.5px;
  color: var(--amber-bright); background: rgba(0, 0, 0, 0.6);
  padding: 2px 8px; border-radius: 5px;
}
.body { flex: 1; display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.ops { display: flex; gap: 8px; margin-top: auto; }
.warn { color: var(--amber-bright); font-family: var(--font-mono); font-size: 12.5px; margin: 0; }
</style>
