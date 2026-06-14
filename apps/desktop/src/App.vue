<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";
import { thumbnailUrl, type Group } from "./api";
import { useEngineStore } from "./stores/engine";
import { useLibraryStore } from "./stores/library";

const engine = useEngineStore();
const library = useLibraryStore();
let timer: number | undefined;

// 终态：就绪或加载失败后不再轮询；其余（连不上/加载中）持续重试
const settled = computed(
  () => engine.phase === "online" && (engine.health?.status === "ready" || engine.health?.status === "error"),
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
  }, 1800);
}
async function reconnect() {
  await engine.refresh();
  if (!settled.value) startPoll();
}

const dot = computed(() => {
  if (engine.phase === "offline") return "offline";
  if (engine.health?.status === "ready") return "ready";
  if (engine.health?.status === "error") return "error";
  return "loading";
});
const label = computed(() => {
  if (engine.phase === "connecting") return "正在连接推理服务…";
  if (engine.phase === "offline") return "连不上推理服务";
  if (engine.health?.status === "ready") return "推理服务就绪";
  if (engine.health?.status === "error") return "模型加载失败";
  return "模型加载中…";
});

const basename = (p: string) => p.split(/[\\/]/).pop() ?? p;

// 层①评分：取某组评分、按分排序、查单张分/是否幸存
const assessmentOf = (id: string) => library.assessments[id];
const scoreOf = (id: string, path: string) => library.assessments[id]?.scoresByPath[path];
const isSurvivor = (id: string, path: string) => assessmentOf(id)?.survivorPaths.includes(path) ?? false;
function orderedPhotos(g: Group): string[] {
  const a = library.assessments[g.id];
  if (!a) return g.photos;
  return [...g.photos].sort((x, y) => (a.scoresByPath[y]?.score ?? -1) - (a.scoresByPath[x]?.score ?? -1));
}

onMounted(async () => {
  await engine.refresh();
  startPoll();
});
onUnmounted(stopPoll);
</script>

<template>
  <main class="app">
    <header class="brand">
      <h1>Keeper <span>· 留影</span></h1>
      <p class="tagline">把最好的留下，留在你自己的电脑里</p>
    </header>

    <!-- 引擎就绪态（紧凑条） -->
    <section class="statusbar">
      <span class="indicator" :class="dot" />
      <span class="status-label">{{ label }}</span>
      <small v-if="engine.health" class="ver">引擎 v{{ engine.health.version }}</small>
      <button class="btn ghost" :disabled="engine.phase === 'connecting'" @click="reconnect">重连</button>
    </section>
    <p v-if="engine.phase === 'offline'" class="hint">
      请先在另一个终端启动推理服务：<code>mise run sidecar</code>
    </p>
    <p v-else-if="engine.health?.status === 'loading'" class="hint">
      首次启动正在下载/载入本地模型，稍候片刻…
    </p>
    <p v-else-if="engine.health?.status === 'error'" class="hint err">{{ engine.health.detail }}</p>

    <!-- 工作区：导入 → 分组 -->
    <section class="workspace">
      <template v-if="!engine.ready">
        <p class="placeholder">服务就绪后即可导入照片目录。</p>
      </template>

      <template v-else-if="!library.imported">
        <div class="import-zone">
          <button class="btn primary" :disabled="library.busy" @click="library.importAndGroup">
            {{ library.busy ? "正在分组…" : "导入照片目录" }}
          </button>
          <p class="hint">选一个文件夹，Keeper 会把相似的连拍聚成「瞬间组」。</p>
          <p v-if="library.error" class="hint err">{{ library.error }}</p>
        </div>
      </template>

      <template v-else>
        <div class="groups-head">
          <strong>{{ library.total }} 张 → {{ library.groups.length }} 个瞬间组</strong>
          <button class="btn ghost" :disabled="library.busy" @click="library.reset">重新导入</button>
        </div>
        <p v-if="library.errors.length" class="hint err">{{ library.errors.length }} 张读取失败</p>
        <div class="groups">
          <article v-for="(g, i) in library.groups" :key="g.id" class="group">
            <header>
              <span>组 {{ i + 1 }} <small>· {{ g.photos.length }} 张</small></span>
              <span class="grow" />
              <small v-if="assessmentOf(g.id)?.busy" class="muted">评分中…</small>
              <small v-else-if="assessmentOf(g.id)" class="muted">
                保底 M={{ assessmentOf(g.id)?.m }} · 进层② {{ assessmentOf(g.id)?.survivorPaths.length }} 张
              </small>
              <button
                v-else
                class="btn ghost"
                :disabled="!engine.ready"
                @click="library.assessGroup(g)"
              >
                评分
              </button>
            </header>
            <p v-if="assessmentOf(g.id)?.error" class="hint err">{{ assessmentOf(g.id)?.error }}</p>
            <div class="thumbs">
              <figure
                v-for="p in orderedPhotos(g)"
                :key="p"
                :class="{
                  survivor: isSurvivor(g.id, p),
                  out: !!assessmentOf(g.id) && !assessmentOf(g.id)?.busy && !isSurvivor(g.id, p),
                }"
                :title="scoreOf(g.id, p) ? scoreOf(g.id, p)!.score + ' · ' + (scoreOf(g.id, p)!.primary_reason || '无明显问题') : basename(p)"
              >
                <img :src="thumbnailUrl(p)" loading="lazy" alt="" />
                <figcaption v-if="scoreOf(g.id, p)">{{ Math.round(scoreOf(g.id, p)!.score) }}</figcaption>
              </figure>
            </div>
          </article>
        </div>
      </template>
    </section>
  </main>
</template>

<style scoped>
.app {
  max-width: 760px;
  margin: 0 auto;
  padding: 48px 24px 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.brand h1 { margin: 0; font-size: 30px; letter-spacing: 0.5px; }
.brand h1 span { color: var(--muted); font-weight: 400; }
.tagline { margin: 6px 0 0; color: var(--muted); font-size: 14px; }

.statusbar {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 14px;
}
.indicator { width: 10px; height: 10px; border-radius: 50%; flex: none; }
.indicator.ready { background: #34d399; }
.indicator.loading { background: #fbbf24; animation: pulse 1.2s infinite; }
.indicator.error { background: #f87171; }
.indicator.offline { background: #6b7280; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
.status-label { font-weight: 500; }
.ver { color: var(--muted); margin-left: auto; }

.btn {
  border: 1px solid var(--border);
  background: transparent;
  color: inherit;
  border-radius: 8px;
  padding: 7px 14px;
  cursor: pointer;
  font: inherit;
  transition: border-color 0.2s, background 0.2s, opacity 0.2s;
}
.btn:hover:not(:disabled) { border-color: #6366f1; background: rgba(99, 102, 241, 0.1); }
.btn:disabled { opacity: 0.5; cursor: default; }
.btn.primary { background: #6366f1; border-color: #6366f1; color: #fff; padding: 11px 22px; font-size: 15px; }
.btn.primary:hover:not(:disabled) { background: #5457e0; }
.btn.ghost { padding: 6px 12px; font-size: 13px; }

.hint { margin: 0; color: var(--muted); font-size: 14px; }
.hint.err { color: #f87171; }
.hint code { background: rgba(255, 255, 255, 0.06); padding: 2px 7px; border-radius: 5px; }
.placeholder { color: var(--muted); }

.import-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 0;
  text-align: center;
}

.groups-head { display: flex; align-items: center; justify-content: space-between; }
.groups { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.group {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
}
.group > header {
  font-weight: 600;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.group > header small { color: var(--muted); font-weight: 400; }
.group > header .grow { flex: 1; }
.muted { color: var(--muted); }
.thumbs { display: flex; flex-wrap: wrap; gap: 8px; }
.thumbs figure {
  position: relative;
  margin: 0;
  width: 96px;
  height: 96px;
  border-radius: 6px;
  overflow: hidden;
  border: 2px solid transparent;
  transition: opacity 0.2s, border-color 0.2s;
}
.thumbs img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  background: #2a2d38;
}
.thumbs figcaption {
  position: absolute;
  left: 4px;
  bottom: 4px;
  padding: 1px 6px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 5px;
  background: rgba(0, 0, 0, 0.66);
  color: #fff;
}
.thumbs figure.survivor { border-color: #34d399; }
.thumbs figure.out { opacity: 0.4; }
</style>

<style>
:root {
  --bg: #14151a;
  --card: #1c1e26;
  --border: #2a2d38;
  --muted: #8b90a0;
  font-family: Inter, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  color: #eef0f5;
  background: var(--bg);
  -webkit-font-smoothing: antialiased;
}
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; }
code { font-family: "SFMono-Regular", Menlo, monospace; }
</style>
