<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "../i18n";
import { useRelease } from "../composables/useRelease";

const { t } = useI18n();
const { urlFor, version } = useRelease();
const c = computed(() => t.value.download);
</script>

<template>
  <section id="download" class="section dl">
    <div class="container">
      <p class="section-kicker">{{ c.kicker }}</p>
      <h2 class="section-title">{{ c.title }}</h2>
      <p class="section-lede">{{ c.lede }}<span v-if="version"> · {{ version }}</span></p>

      <div class="grid">
        <div v-for="(it, i) in c.items" :key="i" class="card item">
          <h3>{{ it.os }}</h3>
          <p class="arch">{{ it.arch }} · {{ it.ext }}</p>
          <a class="btn btn--primary" :href="urlFor(it.match)" target="_blank" rel="noopener">↓ {{ c.button }}</a>
        </div>
      </div>

      <div class="unsigned card">
        <h3>{{ c.unsignedTitle }}</h3>
        <p>{{ c.macUnsigned }}</p>
        <p>{{ c.winUnsigned }}</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.dl { background: linear-gradient(180deg, rgba(226, 161, 58, 0.05), transparent 40%); }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 28px 0 18px; }
.item h3 { font-family: var(--font-display); font-weight: 400; font-size: 20px; margin: 0 0 6px; }
.item .arch { font-family: var(--font-mono); font-size: 12.5px; color: var(--ink-faint); margin: 0 0 18px; }
.unsigned h3 { font-family: var(--font-display); font-weight: 400; font-size: 17px; margin: 0 0 12px; color: var(--amber-bright); }
.unsigned p { color: var(--ink-dim); font-size: 13px; margin: 0 0 8px; line-height: 1.6; }
@media (max-width: 760px) { .grid { grid-template-columns: 1fr; } }
</style>
