<script setup lang="ts">
// 项目主页：列出全部项目（可恢复），入口新建项目，支持删除项目（清副本 + 数据库资源）。
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import type { ProjectView } from "../api";
import { useProjectsStore } from "../stores/projects";
import { fmtTimeRange } from "../util/format";

const store = useProjectsStore();
const router = useRouter();

onMounted(() => store.loadProjects());

const STATUS_LABEL: Record<string, string> = {
  grouping: "分组中",
  selecting: "选片中",
  completed: "已完成",
};

function open(id: number, status: string) {
  router.push(status === "COMPLETED" ? `/projects/${id}/complete` : `/projects/${id}`);
}

// ── 删除确认 ──────────────────────────────────────────────────────────────
const pending = ref<ProjectView | null>(null); // 待确认删除的项目（null=无弹窗）
const deleting = ref(false);

function askDelete(p: ProjectView) {
  pending.value = p;
}

async function confirmDelete() {
  if (!pending.value || deleting.value) return;
  deleting.value = true;
  try {
    await store.remove(pending.value.id);
    pending.value = null;
  } finally {
    deleting.value = false;
  }
}
</script>

<template>
  <section class="home">
    <div class="head">
      <div>
        <h1>选片项目</h1>
        <p class="lede">每次选片是一个项目，进度随时保存——可随时退出、稍后继续。</p>
      </div>
      <div class="actions">
        <RouterLink to="/settings" class="btn">设置</RouterLink>
        <RouterLink to="/new" class="btn btn--primary lg">新建项目</RouterLink>
      </div>
    </div>

    <p v-if="store.error" class="err">{{ store.error }}</p>

    <p v-if="!store.busy && store.list.length === 0" class="empty">
      还没有项目。点「新建项目」选择一个照片文件夹开始。
    </p>

    <ul class="list">
      <li v-for="p in store.list" :key="p.id" class="card" @click="open(p.id, p.status)">
        <div class="title">
          <span class="name">{{ p.name }}</span>
          <span class="status" :class="`s-${p.status}`">{{ STATUS_LABEL[p.status] ?? p.status }}</span>
          <button class="del" title="删除项目" @click.stop="askDelete(p)">删除</button>
        </div>
        <div class="meta">
          <span>{{ p.photo_count }} 张</span>
          <span v-if="p.location">· {{ p.location }}</span>
          <span v-if="fmtTimeRange(p.time_start, p.time_end)">· {{ fmtTimeRange(p.time_start, p.time_end) }}</span>
        </div>
      </li>
    </ul>

    <Teleport to="body">
      <div v-if="pending" class="mask" @click.self="pending = null">
        <div class="dialog">
          <h2>删除项目「{{ pending.name }}」？</h2>
          <p class="warn">
            此操作会删除该项目的<strong>全部存档</strong>（分组、评分、选片进度）以及导入的<strong>照片副本</strong>，且<strong>无法恢复</strong>。
            你的原始照片文件夹不受影响。
          </p>
          <div class="actions">
            <button class="btn" :disabled="deleting" @click="pending = null">取消</button>
            <button class="btn btn--danger" :disabled="deleting" @click="confirmDelete">
              {{ deleting ? "删除中…" : "确认删除" }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.home { display: flex; flex-direction: column; gap: 22px; }
.head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
h1 { margin: 0 0 6px; font-family: var(--font-display); font-weight: 400; font-size: 30px; }
.lede { margin: 0; color: var(--ink-dim); font-size: 13.5px; }
.btn.lg { padding: 11px 22px; font-size: 14px; text-decoration: none; }
.empty { color: var(--ink-faint); font-size: 14px; padding: 30px 0; }
.err { color: var(--red); font-family: var(--font-mono); font-size: 13px; }

/* 响应式网格：窗口越宽排越多列（每列 ≥460px），全屏时用满空间而非拉空单条 */
.list { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(460px, 1fr)); gap: 14px; }
.card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 16px 18px;
  cursor: pointer;
  transition: border-color 0.18s, transform 0.1s;
}
.card:hover { border-color: var(--amber); transform: translateY(-1px); }
.title { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.name { font-family: var(--font-display); font-size: 19px; }
.del {
  margin-left: auto;
  font-family: var(--font-body);
  font-size: 12px;
  color: var(--ink-faint);
  background: transparent;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  padding: 4px 11px;
  cursor: pointer;
  opacity: 0;
  transition: color 0.18s, border-color 0.18s, background 0.18s, opacity 0.18s;
}
.card:hover .del { opacity: 1; }
.del:hover { color: var(--red); border-color: var(--red); background: var(--red-soft); }
.status {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  padding: 2px 9px;
  border-radius: 20px;
  border: 1px solid var(--line-strong);
  color: var(--ink-dim);
}
.status.s-completed { color: var(--green); border-color: var(--green); }
.status.s-selecting { color: var(--amber-bright); border-color: var(--amber); }
.meta { display: flex; gap: 8px; flex-wrap: wrap; color: var(--ink-faint); font-size: 12.5px; font-family: var(--font-mono); }

/* 删除确认弹窗 */
.mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  background: rgba(10, 8, 4, 0.74);
  backdrop-filter: blur(4px);
  animation: fade 0.16s ease;
}
@keyframes fade { from { opacity: 0; } to { opacity: 1; } }
.dialog {
  width: min(440px, 100%);
  background: var(--surface);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 24px;
}
.dialog h2 { margin: 0 0 12px; font-family: var(--font-display); font-weight: 400; font-size: 21px; }
.warn { margin: 0 0 22px; color: var(--ink-dim); font-size: 13.5px; line-height: 1.7; }
.warn strong { color: var(--red); font-weight: 600; }
.actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; }
</style>
