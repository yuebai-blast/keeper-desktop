<script setup lang="ts">
// 分组列表：各组摘要 + 进入；底部一键通过 / 提交完成（全组确认才可提交）。
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useProjectsStore } from "../stores/projects";
import { fmtTimeRange } from "../util/format";
import { photoProgressText } from "../util/progress";
import GroupThumbs from "../components/GroupThumbs.vue";
import ConfirmDialog from "../components/ConfirmDialog.vue";

const props = defineProps<{ id: string }>();
const store = useProjectsStore();
const router = useRouter();
const pid = computed(() => Number(props.id));

const showConfirmAll = ref(false);
const showSubmit = ref(false);

const dropOverKey = ref<string | null>(null);

// 放置：读取被拖照片，落到目标组（同组忽略）；成功后 store 已刷新 detail。
async function onDrop(targetKey: string, e: DragEvent) {
  dropOverKey.value = null;
  const raw = e.dataTransfer?.getData("application/x-keeper-photo");
  if (!raw) return;
  const { photoId, sourceGroupKey } = JSON.parse(raw) as {
    photoId: number;
    sourceGroupKey: string;
  };
  if (sourceGroupKey === targetKey) return; // 拖回原组：无操作
  await store.movePhoto(pid.value, photoId, targetKey);
}

onMounted(async () => {
  await store.loadProject(pid.value);
  // 恢复一个还停在「分组中」的项目：补跑分组
  if (store.detail?.project.status === "GROUPING") await store.runGroup(pid.value);
});

const STATUS: Record<string, string> = { PENDING: "待评测", ASSESSED: "已评测", CONFIRMED: "已确认" };
const confirmedCount = computed(
  () => store.detail?.groups.filter((g) => g.status === "CONFIRMED").length ?? 0,
);
const pendingGroups = computed(() =>
  (store.detail?.groups ?? []).filter((g) => g.status !== "CONFIRMED"),
);
const confirmedGroups = computed(() =>
  (store.detail?.groups ?? []).filter((g) => g.status === "CONFIRMED"),
);
const progressText = computed(() =>
  store.progress ? photoProgressText(store.progress) : "",
);

// 组序号沿用「在全部分组中的原始次序」，避免两区各自从 1 起造成同号歧义
const indexOf = (gk: string) =>
  (store.detail?.groups ?? []).findIndex((g) => g.group_key === gk);

async function doConfirmAll() {
  await store.confirmAll(pid.value);
}

async function doSubmit() {
  if (!store.allConfirmed) return;
  router.push(`/projects/${pid.value}/review`);
}
</script>

<template>
  <section v-if="store.detail" class="groups">
    <RouterLink to="/" class="back">← 全部项目</RouterLink>
    <header class="phead">
      <h1>{{ store.detail.project.name }}</h1>
      <p class="meta">
        <span>{{ store.detail.project.photo_count }} 张 · {{ store.detail.groups.length }} 组</span>
        <span v-if="store.detail.project.location">· {{ store.detail.project.location }}</span>
        <span>· 已确认 {{ confirmedCount }}/{{ store.detail.groups.length }}</span>
      </p>
    </header>

    <p v-if="store.busy" class="muted">处理中…</p>
    <p v-if="store.error" class="err">{{ store.error }}</p>

    <section v-if="pendingGroups.length" class="zone">
      <h2 class="zone-title">待处理 · {{ pendingGroups.length }}</h2>
      <ul class="list">
        <li
          v-for="g in pendingGroups"
          :key="g.group_key"
          class="card"
          :class="{ 'card--drop': dropOverKey === g.group_key }"
          @click="router.push(`/projects/${pid}/groups/${g.group_key}`)"
          @dragover.prevent
          @dragenter.prevent="dropOverKey = g.group_key"
          @dragleave="dropOverKey = (dropOverKey === g.group_key ? null : dropOverKey)"
          @drop="onDrop(g.group_key, $event)"
        >
          <div class="title">
            <span class="gname">组 {{ indexOf(g.group_key) + 1 }}</span>
            <span class="count">{{ g.photo_count }} 张</span>
            <span class="status" :class="`s-${g.status}`">{{ STATUS[g.status] ?? g.status }}</span>
            <span v-if="g.status !== 'PENDING'" class="kept">通过 {{ g.kept_count }}</span>
          </div>
          <div class="sub">
            <span v-if="g.location">{{ g.location }}</span>
            <span v-if="fmtTimeRange(g.time_start, g.time_end)">· {{ fmtTimeRange(g.time_start, g.time_end) }}</span>
          </div>
          <GroupThumbs
            :paths="g.photo_paths"
            :labels="g.photo_names"
            :ids="g.photo_ids"
            :source-group-key="g.group_key"
            :can-drag="true"
          />
        </li>
      </ul>
    </section>

    <section v-if="confirmedGroups.length" class="zone zone--done">
      <h2 class="zone-title">已处理 · {{ confirmedGroups.length }}</h2>
      <ul class="list">
        <li
          v-for="g in confirmedGroups"
          :key="g.group_key"
          class="card"
          @click="router.push(`/projects/${pid}/groups/${g.group_key}`)"
        >
          <div class="title">
            <span class="gname">组 {{ indexOf(g.group_key) + 1 }}</span>
            <span class="count">{{ g.photo_count }} 张</span>
            <span class="status" :class="`s-${g.status}`">{{ STATUS[g.status] ?? g.status }}</span>
            <span class="kept">通过 {{ g.kept_count }}</span>
          </div>
          <div class="sub">
            <span v-if="g.location">{{ g.location }}</span>
            <span v-if="fmtTimeRange(g.time_start, g.time_end)">· {{ fmtTimeRange(g.time_start, g.time_end) }}</span>
          </div>
          <GroupThumbs :paths="g.photo_paths" :labels="g.photo_names" />
        </li>
      </ul>
    </section>

    <footer class="actions">
      <button class="btn" :disabled="store.busy" @click="showConfirmAll = true">一键通过所有分组</button>
      <span class="grow" />
      <button class="btn btn--keep" :disabled="!store.allConfirmed || store.busy" @click="showSubmit = true">
        提交并完成
      </button>
    </footer>
    <div v-if="store.busy && store.progress" class="prog">
      <div class="prog-group" v-if="store.progress.group_count > 1">
        一键通过中… 第 {{ store.progress.group_index }} / {{ store.progress.group_count }} 组
      </div>
      <div class="prog-text">{{ progressText }}</div>
      <div class="prog-bar" :class="{ 'prog-bar--indet': store.progress.total === 0 }">
        <div
          class="prog-fill"
          :style="{ width: store.progress.total ? `${(store.progress.done / store.progress.total) * 100}%` : '100%' }"
        />
      </div>
    </div>
    <p v-if="!store.allConfirmed" class="hint">所有分组都确认后才能提交完成。</p>

    <ConfirmDialog
      v-model:open="showConfirmAll"
      title="一键通过所有分组？"
      confirm-text="继续并开始评分"
      danger
      @confirm="doConfirmAll"
    >
      <p>此操作会：</p>
      <ul>
        <li>对<strong>尚未评测</strong>的分组自动运行<strong>本地初筛</strong>与<strong>AI 精评</strong>；</li>
        <li>按 AI 精评的选择把<strong>所有分组</strong>标记为「已确认」。</li>
      </ul>
      <p>其中 AI 精评会调用外部服务，<strong>可能产生费用</strong>。标记后仍可逐组改回，但需重新逐组检查。</p>
    </ConfirmDialog>

    <ConfirmDialog
      v-model:open="showSubmit"
      title="进入最终预览？"
      confirm-text="去预览"
      @confirm="doSubmit"
    >
      <p>接下来会进入<strong>最终预览</strong>页：可逐张二次调整去留、一键清理杂图，确认后再生成结果。</p>
    </ConfirmDialog>
  </section>
</template>

<style scoped>
.groups { display: flex; flex-direction: column; gap: 16px; }
.back { color: var(--ink-dim); text-decoration: none; font-size: 13px; width: fit-content; }
.back:hover { color: var(--amber-bright); }
.phead h1 { margin: 0 0 4px; font-family: var(--font-display); font-weight: 400; font-size: 26px; }
.meta { margin: 0; display: flex; gap: 7px; flex-wrap: wrap; color: var(--ink-faint); font-size: 12.5px; font-family: var(--font-mono); }
.muted { color: var(--ink-faint); font-size: 13px; }
.err { color: var(--red); font-family: var(--font-mono); font-size: 13px; }

/* 响应式网格：窗口越宽排越多列（每列 ≥420px），全屏时用满空间 */
.list { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 12px; }
.card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 14px 18px;
  cursor: pointer;
  transition: border-color 0.18s, transform 0.1s;
}
.card:hover { border-color: var(--amber); transform: translateY(-1px); }
.card--drop { border-color: var(--amber-bright); background: var(--surface-2); }
.title { display: flex; align-items: center; gap: 11px; }
.gname { font-family: var(--font-display); font-size: 18px; }
.count { font-family: var(--font-mono); font-size: 12px; color: var(--ink-faint); }
.status {
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 2px 9px;
  border-radius: 20px;
  border: 1px solid var(--line-strong);
  color: var(--ink-dim);
}
.status.s-CONFIRMED { color: var(--green); border-color: var(--green); }
.status.s-ASSESSED { color: var(--amber-bright); border-color: var(--amber); }
.kept { font-family: var(--font-mono); font-size: 11.5px; color: var(--green); }
.sub { margin-top: 5px; display: flex; gap: 7px; color: var(--ink-faint); font-size: 12px; font-family: var(--font-mono); }

.actions { display: flex; align-items: center; gap: 12px; padding-top: 10px; border-top: 1px solid var(--line); }
.grow { flex: 1; }
.hint { margin: 0; color: var(--ink-faint); font-size: 12px; text-align: right; }

.zone { display: flex; flex-direction: column; gap: 10px; }
.zone-title {
  margin: 6px 0 0;
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-faint);
}
.zone--done { margin-top: 6px; padding-top: 14px; border-top: 1px solid var(--line); }
.zone--done .card { opacity: 0.62; }
.zone--done .card:hover { opacity: 1; }

.prog { margin-top: 12px; display: flex; flex-direction: column; gap: 6px; max-width: 360px; }
.prog-group { font-family: var(--font-mono); font-size: 12.5px; color: var(--amber-bright); }
.prog-text { font-family: var(--font-mono); font-size: 12.5px; color: var(--ink-dim); }
.prog-bar { height: 6px; border-radius: 4px; background: var(--line); overflow: hidden; }
.prog-fill { height: 100%; background: var(--amber); transition: width 0.3s ease; }
/* 聚类阶段（total=0）：填满 + 脉动，表达「进行中但无精确百分比」的不确定态 */
.prog-bar--indet .prog-fill { animation: prog-pulse 1.1s ease-in-out infinite; }
@keyframes prog-pulse { 0%, 100% { opacity: 0.35; } 50% { opacity: 1; } }
</style>
