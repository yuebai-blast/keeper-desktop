<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "../i18n";
const { t } = useI18n();
const c = computed(() => t.value.footer);
const REPO = "https://github.com/yuebai-blast/keeper";
</script>

<template>
  <footer class="ft">
    <div class="container row">
      <div>
        <span class="logo">留影 Keeper</span>
        <p class="tag">{{ c.tagline }}</p>
        <p class="lic">{{ c.license }}</p>
      </div>
      <nav class="links">
        <a href="#download">{{ c.download }}</a>
        <a :href="REPO" target="_blank" rel="noopener">{{ c.github }}</a>
        <a :href="`${REPO}#readme`" target="_blank" rel="noopener">{{ c.docs }}</a>
      </nav>
    </div>
    <div class="container copy">{{ c.copyright }}</div>
  </footer>
</template>

<style scoped>
.ft { border-top: 1px solid var(--line); padding: 48px 0 30px; margin-top: 40px; }
.row { display: flex; justify-content: space-between; gap: 24px; flex-wrap: wrap; }
.logo { font-family: var(--font-display); font-size: 19px; }
.tag { color: var(--ink-dim); margin: 10px 0 6px; max-width: 360px; }
.lic { font-family: var(--font-mono); font-size: 11.5px; color: var(--ink-faint); margin: 0; }
.links { display: flex; gap: 20px; height: fit-content; }
.links a { color: var(--ink-dim); }
.links a:hover { color: var(--amber-bright); }
.copy { font-family: var(--font-mono); font-size: 12px; color: var(--ink-faint); margin-top: 28px; }
</style>
