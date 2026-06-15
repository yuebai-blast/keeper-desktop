<script setup lang="ts">
// 分组列表：各组摘要 + 进入；底部一键通过 / 提交完成（全组确认才可提交）。
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useProjectsStore } from "../stores/projects";
import { fmtTimeRange } from "../util/format";
import GroupThumbs from "../components/GroupThumbs.vue";

const props = defineProps<{ id: string }>();
const store = useProjectsStore();
const router = useRouter();
const pid = computed(() => Number(props.id));

onMounted(async () => {
  await store.loadProject(pid.value);
  // 恢复一个还停在「分组中」的项目：补跑分组
  if (store.detail?.project.status === "grouping") await store.runGroup(pid.value);
});

const STATUS: Record<string, string> = { pending: "待评测", assessed: "已评测", confirmed: "已确认" };
const confirmedCount = computed(
  () => store.detail?.groups.filter((g) => g.status === "confirmed").length ?? 0,
);

async function confirmAll() {
  if (!window.confirm("一键通过会对尚未评测的分组调用大模型评分（可能产生费用），并把所有分组按大模型的选择标记为已确认。继续？")) return;
  await store.confirmAll(pid.value);
}

async function submit() {
  if (!store.allConfirmed) return;
  if (!window.confirm("提交后将把所有「通过」的照片复制到输出目录，并删除 workspace 副本释放空间。确认完成？")) return;
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

    <ul class="list">
      <li
        v-for="(g, i) in store.detail.groups"
        :key="g.group_key"
        class="card"
        @click="router.push(`/projects/${pid}/groups/${g.group_key}`)"
      >
        <div class="title">
          <span class="gname">组 {{ i + 1 }}</span>
          <span class="count">{{ g.photo_count }} 张</span>
          <span class="status" :class="`s-${g.status}`">{{ STATUS[g.status] ?? g.status }}</span>
          <span v-if="g.status !== 'pending'" class="kept">通过 {{ g.kept_count }}</span>
        </div>
        <div class="sub">
          <span v-if="g.location">{{ g.location }}</span>
          <span v-if="fmtTimeRange(g.time_start, g.time_end)">· {{ fmtTimeRange(g.time_start, g.time_end) }}</span>
        </div>
        <GroupThumbs :paths="g.photo_paths" :labels="g.photo_names" />
      </li>
    </ul>

    <footer class="actions">
      <button class="btn" :disabled="store.busy" @click="confirmAll">一键通过所有分组</button>
      <span class="grow" />
      <button class="btn btn--keep" :disabled="!store.allConfirmed || store.busy" @click="submit">
        提交并完成
      </button>
    </footer>
    <p v-if="!store.allConfirmed" class="hint">所有分组都确认后才能提交完成。</p>
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

.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 11px; }
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
.status.s-confirmed { color: var(--green); border-color: var(--green); }
.status.s-assessed { color: var(--amber-bright); border-color: var(--amber); }
.kept { font-family: var(--font-mono); font-size: 11.5px; color: var(--green); }
.sub { margin-top: 5px; display: flex; gap: 7px; color: var(--ink-faint); font-size: 12px; font-family: var(--font-mono); }

.actions { display: flex; align-items: center; gap: 12px; padding-top: 10px; border-top: 1px solid var(--line); }
.grow { flex: 1; }
.hint { margin: 0; color: var(--ink-faint); font-size: 12px; text-align: right; }
</style>
