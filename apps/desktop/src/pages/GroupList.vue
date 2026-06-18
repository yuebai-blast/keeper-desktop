<script setup lang="ts">
// 分组列表：各组摘要 + 进入；底部一键通过 / 提交完成（全组确认才可提交）。
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useProjectsStore } from "../stores/projects";
import { fmtTimeRange } from "../util/format";
import GroupThumbs from "../components/GroupThumbs.vue";
import ConfirmDialog from "../components/ConfirmDialog.vue";

const props = defineProps<{ id: string }>();
const store = useProjectsStore();
const router = useRouter();
const pid = computed(() => Number(props.id));

const showConfirmAll = ref(false);
const showSubmit = ref(false);

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
// 组序号沿用「在全部分组中的原始次序」，避免两区各自从 1 起造成同号歧义
const indexOf = (gk: string) =>
  (store.detail?.groups ?? []).findIndex((g) => g.group_key === gk);

async function doConfirmAll() {
  await store.confirmAll(pid.value);
}

async function doSubmit() {
  if (!store.allConfirmed) return;
  await store.complete(pid.value);
  router.push(`/projects/${pid.value}/complete`);
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
          @click="router.push(`/projects/${pid}/groups/${g.group_key}`)"
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
          <GroupThumbs :paths="g.photo_paths" :labels="g.photo_names" />
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
        <li>对<strong>尚未评测</strong>的分组自动运行本地评分（层①）与<strong>在线大模型评分</strong>（层②）；</li>
        <li>按大模型的选择把<strong>所有分组</strong>标记为「已确认」。</li>
      </ul>
      <p>其中在线大模型评分会调用外部服务，<strong>可能产生费用</strong>。标记后仍可逐组改回，但需重新逐组检查。</p>
    </ConfirmDialog>

    <ConfirmDialog
      v-model:open="showSubmit"
      title="提交并完成？"
      confirm-text="确认完成"
      @confirm="doSubmit"
    >
      <p>提交后会把所有「通过」的照片复制到输出目录，并删除 workspace 副本释放空间。</p>
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
</style>
