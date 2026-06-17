<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "../i18n";
const { t } = useI18n();
const c = computed(() => t.value.showcase);
// 实机截图后把这两张图放到 public/screenshots/ 并改用真实文件名
const shots = ["/screenshots/group-detail.png", "/screenshots/arena.png"];
</script>

<template>
  <section class="section">
    <div class="container">
      <p class="section-kicker">{{ c.kicker }}</p>
      <h2 class="section-title">{{ c.title }}</h2>
      <p class="section-lede">{{ c.lede }}</p>

      <div class="shots">
        <figure v-for="(src, i) in shots" :key="i" class="shot">
          <img :src="src" :alt="c.shotAlt[i]" loading="lazy" onerror="this.style.opacity=0.15" />
          <figcaption>{{ c.shotAlt[i] }}</figcaption>
        </figure>
      </div>

      <div class="reqs card">
        <h3>{{ c.reqTitle }}</h3>
        <ul>
          <li v-for="(r, i) in c.reqs" :key="i">{{ r }}</li>
        </ul>
      </div>
    </div>
  </section>
</template>

<style scoped>
.shots { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin: 28px 0; }
.shot { margin: 0; }
.shot img { width: 100%; aspect-ratio: 16/10; object-fit: cover; border-radius: var(--radius); border: 1px solid var(--line); background: var(--surface); }
.shot figcaption { font-family: var(--font-mono); font-size: 12px; color: var(--ink-faint); margin-top: 8px; }
.reqs h3 { font-family: var(--font-display); font-weight: 400; font-size: 19px; margin: 0 0 12px; }
.reqs ul { margin: 0; padding-left: 18px; color: var(--ink-dim); }
.reqs li { margin-bottom: 8px; line-height: 1.6; }
@media (max-width: 760px) { .shots { grid-template-columns: 1fr; } }
</style>
