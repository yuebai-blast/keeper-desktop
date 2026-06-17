<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "../i18n";
const { t } = useI18n();
const c = computed(() => t.value.features);
</script>

<template>
  <section id="features" class="section">
    <div class="container">
      <p class="section-kicker">{{ c.kicker }}</p>
      <h2 class="section-title">{{ c.title }}</h2>
      <div class="grid">
        <div v-for="(it, i) in c.items" :key="i" class="card">
          <h3>{{ it.title }}</h3>
          <p>{{ it.body }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 28px; }
.card h3 { font-family: var(--font-display); font-weight: 400; font-size: 19px; margin: 0 0 9px; }
.card p { color: var(--ink-dim); font-size: 13.5px; margin: 0; line-height: 1.65; }
.card:hover { border-color: var(--amber); transform: translateY(-1px); }
@media (max-width: 860px) { .grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 480px) { .grid { grid-template-columns: 1fr; } }
</style>
