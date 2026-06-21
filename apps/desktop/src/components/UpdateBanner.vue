<script setup lang="ts">
// 在线升级的非阻塞提示横幅：发现新版时从顶栏下方滑入，不打断用户当前操作。
// 用户可「更新」（后台下载，显示进度）或「稍后」（关掉，设置页仍可手动再查）；
// 下载完成后提示重启生效。启动静默检查由 App.vue 触发，失败不展示本横幅。
import { useUpdaterStore } from "../stores/updater";

const updater = useUpdaterStore();
</script>

<template>
  <!-- available：发现新版，待用户决定 -->
  <div v-if="updater.showBanner" class="bar">
    <span class="dot" />
    <span class="msg">发现新版本 <b>v{{ updater.version }}</b>，建议更新。</span>
    <span class="grow" />
    <button class="btn" @click="updater.dismiss()">稍后</button>
    <button class="btn btn--primary" @click="updater.downloadAndInstall()">更新</button>
  </div>

  <!-- downloading：后台下载中，显示进度 -->
  <div v-else-if="updater.phase === 'downloading'" class="bar">
    <span class="dot" />
    <span class="msg">正在下载更新… {{ updater.percent }}%</span>
    <span class="grow" />
    <div class="track"><i :style="{ width: updater.percent + '%' }" /></div>
  </div>

  <!-- ready：已装好，待重启生效 -->
  <div v-else-if="updater.phase === 'ready'" class="bar">
    <span class="dot dot--ok" />
    <span class="msg">新版本已就绪，重启应用即可生效。</span>
    <span class="grow" />
    <button class="btn btn--primary" @click="updater.restart()">立即重启</button>
  </div>
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  margin-bottom: 10px;
  background: var(--surface);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--ink);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--amber);
  box-shadow: 0 0 8px var(--amber);
  flex: none;
}
.dot--ok {
  background: var(--green);
  box-shadow: 0 0 8px var(--green);
}
.msg b {
  font-weight: 600;
  color: var(--amber-bright);
}
.grow {
  flex: 1;
}
.track {
  width: 160px;
  height: 5px;
  border-radius: 3px;
  background: var(--line);
  overflow: hidden;
  flex: none;
}
.track i {
  display: block;
  height: 100%;
  background: var(--amber);
  transition: width 0.2s ease;
}
</style>
