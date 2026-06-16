<script setup lang="ts">
// 设置页（自用版）：配置 Ark 大模型 key / 模型 id / 接口基址。
// 自用版让用户填自己的 key 直连大模型；商业版构建移除此页（key 在云端中转，不下发客户端）。
import { onMounted, ref } from "vue";
import { getSettings, saveSettings } from "../api";

const loading = ref(true);
const saving = ref(false);
const error = ref("");
const saved = ref(false);

// 表单字段
const arkKey = ref(""); // 留空=不改既有 key
const keyAlreadySet = ref(false); // 后端是否已存在 key（决定占位文案）
const arkModel = ref("");
const arkBaseUrl = ref("");

onMounted(async () => {
  try {
    const s = await getSettings();
    arkModel.value = s.ark_model;
    arkBaseUrl.value = s.ark_base_url;
    keyAlreadySet.value = s.ark_key_set;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
});

async function save() {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
  saved.value = false;
  try {
    // ark_key 仅在用户输入了内容时提交，留空则保持原 key 不变
    const s = await saveSettings({
      ark_key: arkKey.value.trim() || undefined,
      ark_model: arkModel.value.trim(),
      ark_base_url: arkBaseUrl.value.trim(),
    });
    arkModel.value = s.ark_model;
    arkBaseUrl.value = s.ark_base_url;
    keyAlreadySet.value = s.ark_key_set;
    arkKey.value = ""; // 清空输入框，避免明文驻留
    saved.value = true;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section class="settings">
    <RouterLink to="/" class="back">← 返回</RouterLink>
    <h1>设置</h1>

    <p class="lede">配置在线大模型（火山 Ark，OpenAI 兼容协议）打分所需的凭据与模型。</p>

    <div v-if="loading" class="muted">正在加载…</div>

    <template v-else>
      <label class="field">
        <span>Ark API Key</span>
        <input
          v-model="arkKey"
          type="password"
          autocomplete="off"
          :placeholder="keyAlreadySet ? '已配置 —— 留空则保持不变' : '粘贴你的 Ark API Key'"
          :disabled="saving"
        />
        <small>仅保存在本机 ~/.keeper/ark_key（0600 权限），绝不入库、绝不上传。</small>
      </label>

      <label class="field">
        <span>模型 id</span>
        <input
          v-model="arkModel"
          type="text"
          placeholder="例如：ep-xxxxxxxx 或具体模型名"
          :disabled="saving"
        />
        <small>火山方舟「接入点」id 或模型名，用于层②照片打分。</small>
      </label>

      <label class="field">
        <span>接口基址</span>
        <input v-model="arkBaseUrl" type="text" :disabled="saving" />
        <small>一般无需修改；默认火山 Ark 北京区。</small>
      </label>

      <p v-if="error" class="err">{{ error }}</p>
      <p v-if="saved" class="ok">已保存 ✓</p>

      <button class="btn btn--primary lg" :disabled="saving" @click="save">
        {{ saving ? "正在保存…" : "保存" }}
      </button>
    </template>
  </section>
</template>

<style scoped>
.settings { display: flex; flex-direction: column; gap: 20px; max-width: 620px; }
.back { color: var(--ink-dim); text-decoration: none; font-size: 13px; width: fit-content; }
.back:hover { color: var(--amber-bright); }
h1 { margin: 0; font-family: var(--font-display); font-weight: 400; font-size: 28px; }
.lede { margin: -8px 0 0; color: var(--ink-dim); font-size: 13.5px; }
.field { display: flex; flex-direction: column; gap: 8px; }
.field > span { font-size: 13px; color: var(--ink-dim); }
.field small { color: var(--ink-faint); font-size: 12px; }
input {
  font-family: var(--font-body);
  font-size: 14px;
  color: var(--ink);
  background: var(--surface);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  padding: 11px 14px;
}
input:focus { outline: none; border-color: var(--amber); }
.muted { color: var(--ink-faint); font-size: 13px; }
.err { color: var(--red); font-family: var(--font-mono); font-size: 13px; margin: 0; }
.ok { color: var(--amber-bright); font-size: 13px; margin: 0; }
.btn.lg { padding: 12px 24px; font-size: 14.5px; width: fit-content; }
</style>
