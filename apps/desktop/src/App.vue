<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { thumbnailUrl, type Group } from "./api";
import Arena from "./components/Arena.vue";
import SplashView from "./components/SplashView.vue";
import { useEngineStore } from "./stores/engine";
import { useLibraryStore } from "./stores/library";

const engine = useEngineStore();
const library = useLibraryStore();

// 用户是否已穿过加载页进入应用（加载页 ready 后自动/点按钮置位）
const entered = ref(false);

let timer: number | undefined;
// 终态：就绪、或不可重试的致命错误后停止轮询；其余（连不上/加载中/可重试）持续刷新
const settled = computed(
  () =>
    engine.phase === "online" &&
    (engine.health?.status === "ready" ||
      (engine.health?.status === "error" && engine.health?.retryable === false)),
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
  }, 800);
}

const basename = (p: string) => p.split(/[\\/]/).pop() ?? p;

// 层①评分
const assessmentOf = (id: string) => library.assessments[id];
const scoreOf = (id: string, path: string) => library.assessments[id]?.scoresByPath[path];
const isSurvivor = (id: string, path: string) => assessmentOf(id)?.survivorPaths.includes(path) ?? false;
function orderedPhotos(g: Group): string[] {
  const a = library.assessments[g.id];
  if (!a) return g.photos;
  return [...g.photos].sort((x, y) => (a.scoresByPath[y]?.score ?? -1) - (a.scoresByPath[x]?.score ?? -1));
}

// 擂台
const arenaGroup = ref<Group | null>(null);
const decisionOf = (id: string) => library.decisions[id];
function onArenaFinish(winner: string | null, losers: string[]) {
  if (arenaGroup.value) library.decideGroup(arenaGroup.value.id, winner, losers);
  arenaGroup.value = null;
}

// 穿过加载页进入应用；修复完成（重新加载页 emit enter）时一并清掉修复标记
function onEnter() {
  entered.value = true;
  engine.clearRepair();
}
// 运行时触发修复（needsRepair）→ 重新加载已转 loading，重启轮询刷新进度
watch(
  () => engine.needsRepair,
  (v) => {
    if (v) startPoll();
  },
);

onMounted(async () => {
  await engine.refresh();
  startPoll();
});
onUnmounted(stopPoll);
</script>

<template>
  <SplashView v-if="!entered || engine.needsRepair" @enter="onEnter" />

  <main v-else class="app">
    <header class="topbar">
      <div class="wordmark">
        <span class="k">Keeper</span>
        <span class="cn">留影</span>
      </div>
      <span class="ready"><i /> 就绪</span>
      <span class="grow" />
      <template v-if="library.imported">
        <span class="stat">
          {{ library.total }} 张 · {{ library.groups.length }} 组 ·
          已裁 {{ library.decidedCount }}/{{ library.groups.length }}
        </span>
        <button class="btn btn--ghost" :disabled="library.busy" @click="library.reset">重新导入</button>
      </template>
    </header>

    <!-- 未导入：导入英雄区 -->
    <section v-if="!library.imported" class="hero">
      <div class="viewfinder">
        <span class="corner tl" /><span class="corner tr" />
        <span class="corner bl" /><span class="corner br" />
        <p class="kicker">第 0 步 · 分组</p>
        <h2>导入一个照片目录</h2>
        <p class="lede">Keeper 会把相似的连拍聚成「瞬间组」，为每组递上一份足够好的候选——留谁，由你定。</p>
        <button class="btn btn--primary lg" :disabled="library.busy" @click="library.importAndGroup">
          {{ library.busy ? "正在分组…" : "选择照片目录" }}
        </button>
        <p v-if="library.error" class="err">{{ library.error }}</p>
      </div>
    </section>

    <!-- 已导入：归档条 + 组列表 -->
    <section v-else class="workspace">
      <p v-if="library.errors.length" class="note err">{{ library.errors.length }} 张读取失败</p>

      <div v-if="library.decidedCount" class="archive">
        <span class="archive-label">归档 {{ library.decidedCount }} 组裁决</span>
        <button class="btn btn--ghost" :disabled="library.archiving" @click="library.archive('copy')">复制</button>
        <button class="btn btn--ghost" :disabled="library.archiving" @click="library.archive('move')">移动</button>
        <button class="btn btn--ghost" :disabled="library.archiving" @click="library.archive('manifest')">仅清单</button>
        <span class="grow" />
        <span v-if="library.archiving" class="muted">归档中…</span>
        <span v-else-if="library.archiveSummary" class="ok">
          ✓ 留 {{ library.archiveSummary.winners }} · 弃 {{ library.archiveSummary.losers }}
          <template v-if="library.archiveSummary.errors.length">· {{ library.archiveSummary.errors.length }} 失败</template>
        </span>
        <span v-if="library.archiveError" class="err">{{ library.archiveError }}</span>
      </div>

      <div class="groups">
        <article v-for="(g, i) in library.groups" :key="g.id" class="group" :class="{ decided: !!decisionOf(g.id) }">
          <header>
            <span class="gtitle">组 {{ i + 1 }}<small>{{ g.photos.length }} 张</small></span>
            <span class="grow" />
            <small v-if="assessmentOf(g.id)?.busy" class="muted">评分中…</small>
            <small v-else-if="assessmentOf(g.id)" class="muted">
              M={{ assessmentOf(g.id)?.m }} · 进层② {{ assessmentOf(g.id)?.survivorPaths.length }} 张
            </small>
            <button v-else class="btn btn--ghost" :disabled="!engine.ready" @click="library.assessGroup(g)">
              评分
            </button>
            <button v-if="!decisionOf(g.id)" class="btn btn--ghost" @click="arenaGroup = g">进擂台</button>
            <span v-else class="verdict" :class="decisionOf(g.id)?.winner ? 'keep' : 'drop'">
              {{ decisionOf(g.id)?.winner ? "✓ 已选定" : "✕ 已舍弃" }}
            </span>
          </header>
          <p v-if="assessmentOf(g.id)?.error" class="note err">{{ assessmentOf(g.id)?.error }}</p>
          <div class="thumbs">
            <figure
              v-for="p in orderedPhotos(g)"
              :key="p"
              :class="{
                survivor: !decisionOf(g.id) && isSurvivor(g.id, p),
                out: !decisionOf(g.id) && !!assessmentOf(g.id) && !assessmentOf(g.id)?.busy && !isSurvivor(g.id, p),
                chosen: decisionOf(g.id)?.winner === p,
                discarded: !!decisionOf(g.id) && decisionOf(g.id)?.winner !== p,
              }"
              :title="scoreOf(g.id, p) ? scoreOf(g.id, p)!.score + ' · ' + (scoreOf(g.id, p)!.primary_reason || '无明显问题') : basename(p)"
            >
              <img :src="thumbnailUrl(p)" loading="lazy" alt="" />
              <figcaption v-if="scoreOf(g.id, p)">{{ Math.round(scoreOf(g.id, p)!.score) }}</figcaption>
            </figure>
          </div>
        </article>
      </div>
    </section>
  </main>

  <Arena
    v-if="arenaGroup"
    :candidates="library.candidatesOf(arenaGroup!)"
    @finish="onArenaFinish"
    @close="arenaGroup = null"
  />
</template>

<style scoped>
.app {
  max-width: 980px;
  margin: 0 auto;
  padding: 0 28px 64px;
}

/* 顶栏 */
.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px 0 16px;
  margin-bottom: 8px;
  background: linear-gradient(var(--bg) 72%, transparent);
  backdrop-filter: blur(2px);
}
.wordmark { display: flex; align-items: baseline; gap: 9px; }
.wordmark .k {
  font-family: var(--font-display);
  font-weight: 400;
  font-size: 23px;
  letter-spacing: 0.01em;
}
.wordmark .cn {
  font-family: var(--font-display);
  font-size: 13px;
  color: var(--amber);
  letter-spacing: 0.28em;
  padding-left: 0.28em;
}
.ready {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ink-faint);
  font-family: var(--font-mono);
  letter-spacing: 0.05em;
}
.ready i { width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 8px var(--green); }
.grow { flex: 1; }
.stat { font-size: 12.5px; color: var(--ink-dim); font-family: var(--font-mono); letter-spacing: 0.02em; }

/* 导入英雄区 */
.hero { display: flex; justify-content: center; padding: 8vh 0 0; }
.viewfinder {
  position: relative;
  max-width: 540px;
  padding: 56px 52px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}
.viewfinder .corner {
  position: absolute;
  width: 24px; height: 24px;
  border: 2px solid var(--line-strong);
}
.viewfinder .corner.tl { top: 0; left: 0; border-right: 0; border-bottom: 0; }
.viewfinder .corner.tr { top: 0; right: 0; border-left: 0; border-bottom: 0; }
.viewfinder .corner.bl { bottom: 0; left: 0; border-right: 0; border-top: 0; }
.viewfinder .corner.br { bottom: 0; right: 0; border-left: 0; border-top: 0; }
.kicker {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 11.5px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--amber);
}
.viewfinder h2 {
  margin: 0;
  font-family: var(--font-display);
  font-weight: 380;
  font-size: 38px;
  letter-spacing: 0.01em;
}
.lede { margin: 0 0 8px; color: var(--ink-dim); font-size: 14px; line-height: 1.65; max-width: 420px; }
.btn.lg { padding: 12px 26px; font-size: 14.5px; }
.err { color: var(--red); font-size: 13px; font-family: var(--font-mono); }

/* 工作区 */
.note { margin: 0 0 12px; font-size: 13px; }
.note.err { color: var(--red); }

.archive {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px 16px;
  margin-bottom: 18px;
}
.archive-label { font-size: 13px; color: var(--ink-dim); margin-right: 4px; }
.archive .muted { color: var(--ink-faint); font-size: 13px; }
.archive .ok { color: var(--green); font-size: 13px; }
.archive .err { font-size: 12.5px; }

.groups { display: flex; flex-direction: column; gap: 16px; }
.group {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 16px 18px;
  box-shadow: var(--shadow);
  transition: border-color 0.2s, opacity 0.2s;
}
.group.decided { opacity: 0.82; }
.group > header { display: flex; align-items: center; gap: 10px; margin-bottom: 13px; }
.gtitle {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 420;
  display: inline-flex;
  align-items: baseline;
  gap: 9px;
}
.gtitle small { font-family: var(--font-mono); font-size: 11.5px; color: var(--ink-faint); letter-spacing: 0.04em; }
.muted { color: var(--ink-faint); font-size: 12.5px; font-family: var(--font-mono); }
.verdict { font-size: 12.5px; font-weight: 500; }
.verdict.keep { color: var(--green); }
.verdict.drop { color: var(--ink-faint); }

.thumbs { display: flex; flex-wrap: wrap; gap: 9px; }
.thumbs figure {
  position: relative;
  margin: 0;
  width: 104px;
  height: 104px;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid transparent;
  transition: opacity 0.25s, border-color 0.2s, transform 0.12s, box-shadow 0.2s;
}
.thumbs figure:hover { transform: translateY(-2px); }
.thumbs img { width: 100%; height: 100%; object-fit: cover; display: block; background: var(--surface-2); }
.thumbs figcaption {
  position: absolute;
  left: 5px;
  bottom: 5px;
  padding: 1px 7px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 500;
  border-radius: 5px;
  background: rgba(0, 0, 0, 0.7);
  color: var(--amber-bright);
  backdrop-filter: blur(2px);
}
.thumbs figure.survivor { border-color: var(--amber); box-shadow: 0 0 0 1px var(--amber-soft); }
.thumbs figure.out { opacity: 0.34; }
.thumbs figure.chosen { border-color: var(--green); box-shadow: 0 0 0 3px var(--green-soft); }
.thumbs figure.chosen figcaption { color: var(--green); }
.thumbs figure.discarded { opacity: 0.26; }
</style>
