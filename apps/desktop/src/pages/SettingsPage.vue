<script setup lang="ts">
// 设置页（自用版）：配置 Ark 大模型 key / 模型 id / 接口基址。
// 「能连上才给保存」：先测试连接（key+模型实调一次），成功后才允许保存；改任一字段需重测。
// 自用版让用户填自己的 key 直连大模型；商业版构建移除此页（key 在云端中转，不下发客户端）。
import { openUrl } from "@tauri-apps/plugin-opener";
import { getVersion } from "@tauri-apps/api/app";
import { nextTick, onMounted, ref, watch } from "vue";
import { getSettings, listVisionModels, saveSettings, testSettings, type VisionModel } from "../api";
import { useUpdaterStore } from "../stores/updater";

// 在线升级：手动检查（启动静默检查在 App.vue）。结果/进度复用 updater store，与顶栏横幅联动。
const updater = useUpdaterStore();
const appVersion = ref("");
const checkedOnce = ref(false); // 是否手动点过检查（用于区分「未查」与「已是最新」）

async function checkUpdate() {
  checkedOnce.value = true;
  await updater.check(false);
}

// 控制台指引链接（用系统浏览器打开）
const ARK_APIKEY_URL = "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey";
const VOLC_AKSK_URL = "https://console.volcengine.com/iam/keymanage";

const loading = ref(true);
const testing = ref(false);
const saving = ref(false);
const tested = ref(false); // 当前字段值是否已通过连接测试（改字段即失效）
const error = ref("");
const saved = ref(false);

// 表单字段
const arkKey = ref(""); // 留空=不改既有 key
const keyAlreadySet = ref(false); // 后端是否已存在 key（决定占位文案）
const arkModel = ref("");
const arkBaseUrl = ref("");

// 「拉取视觉模型」辅助（可选）：用火山 AK/SK 调管理面列出支持图片理解的模型，下拉回填 model id。
// AK/SK 与打分用的 key 是两套；全程可选，手填 model id 永远兜底。
const volcAk = ref(""); // 留空=用已存的
const volcSk = ref("");
const volcCredsSet = ref(false); // 后端是否已存在 AK/SK
const fetching = ref(false);
const fetchError = ref("");
const models = ref<VisionModel[]>([]);
const pickedModel = ref(""); // 下拉当前选中的 model_id

// 改动任一字段 → 作废上次测试结果与提示（须重新测试才能保存）
let suppress = false; // 程序化回填字段时不触发作废
watch([arkKey, arkModel, arkBaseUrl], () => {
  if (suppress) return;
  tested.value = false;
  saved.value = false;
  error.value = "";
});

onMounted(async () => {
  try {
    appVersion.value = await getVersion();
  } catch {
    appVersion.value = "";
  }
  try {
    const s = await getSettings();
    suppress = true;
    arkModel.value = s.ark_model;
    arkBaseUrl.value = s.ark_base_url;
    keyAlreadySet.value = s.ark_key_set;
    volcCredsSet.value = s.volc_credentials_set;
    await nextTick();
    suppress = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
});

/** 拉取支持图片理解的模型；成功后 AK/SK 落盘复用，清空输入框避免明文驻留。 */
async function fetchModels() {
  if (fetching.value) return;
  fetching.value = true;
  fetchError.value = "";
  try {
    const { items } = await listVisionModels({
      volc_ak: volcAk.value.trim() || undefined,
      volc_sk: volcSk.value.trim() || undefined,
    });
    models.value = items;
    volcCredsSet.value = true;
    volcAk.value = "";
    volcSk.value = "";
  } catch (e) {
    fetchError.value = e instanceof Error ? e.message : String(e);
  } finally {
    fetching.value = false;
  }
}

/** 选中下拉里的模型 → 回填到 model id 输入框（改 model 会作废上次连接测试，符合预期）。 */
function pickModel() {
  if (pickedModel.value) arkModel.value = pickedModel.value;
}

/** 当前表单值（key 留空则后端用已存 key）。 */
function payload() {
  return {
    ark_key: arkKey.value.trim() || undefined,
    ark_model: arkModel.value.trim(),
    ark_base_url: arkBaseUrl.value.trim(),
  };
}

async function testConn() {
  if (testing.value) return;
  testing.value = true;
  error.value = "";
  saved.value = false;
  try {
    await testSettings(payload());
    tested.value = true;
  } catch (e) {
    tested.value = false;
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    testing.value = false;
  }
}

async function save() {
  if (saving.value || !tested.value) return;
  saving.value = true;
  error.value = "";
  try {
    // 后端会再测一次（先测后存），测不通不落配置——双保险
    const s = await saveSettings(payload());
    suppress = true;
    arkKey.value = ""; // 清空输入框，避免明文驻留
    arkModel.value = s.ark_model;
    arkBaseUrl.value = s.ark_base_url;
    keyAlreadySet.value = s.ark_key_set;
    tested.value = false; // 已存盘，无新改动可存
    saved.value = true;
    await nextTick();
    suppress = false;
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

    <p class="lede">填入火山方舟大模型的 API Key 和模型，用于给照片智能打分。</p>

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
        <small>
          只存在你这台电脑上，不上传、不外泄。
          <a class="link" @click="openUrl(ARK_APIKEY_URL)">→ 去火山控制台获取 API Key</a>
        </small>
      </label>

      <label class="field">
        <span>模型 id</span>
        <input
          v-model="arkModel"
          type="text"
          placeholder="例如：ep-xxxxxxxx 或具体模型名"
          :disabled="saving"
        />
        <small>火山方舟「接入点」id 或模型名，用于 AI 精评给照片打分。可手填，或用下方「拉取视觉模型」辅助选。</small>
      </label>

      <details class="helper">
        <summary>不知道填哪个模型？用火山 AK/SK 拉取支持图片理解的模型（可选）</summary>
        <div class="helper__body">
          <p class="muted">
            AK/SK 只用来列出可选模型，<strong>不参与打分</strong>。和上面的 Key 一样只存在你这台电脑上、不外泄。已填过可留空直接拉取。
            <a class="link" @click="openUrl(VOLC_AKSK_URL)">→ 去火山控制台获取 AK/SK</a>
          </p>
          <div class="creds">
            <input
              v-model="volcAk"
              type="password"
              autocomplete="off"
              :placeholder="volcCredsSet ? 'Access Key（已配置，留空沿用）' : 'Access Key'"
              :disabled="fetching"
            />
            <input
              v-model="volcSk"
              type="password"
              autocomplete="off"
              :placeholder="volcCredsSet ? 'Secret Key（已配置，留空沿用）' : 'Secret Key'"
              :disabled="fetching"
            />
            <button class="btn" :disabled="fetching" @click="fetchModels">
              {{ fetching ? "拉取中…" : "拉取视觉模型" }}
            </button>
          </div>

          <label v-if="models.length" class="field">
            <span>选择视觉模型（{{ models.length }} 个）</span>
            <select v-model="pickedModel" @change="pickModel" :disabled="saving">
              <option value="" disabled>▼ 选一个回填到上面的「模型 id」</option>
              <option v-for="m in models" :key="m.model_id" :value="m.model_id">
                {{ m.display_name }} —— {{ m.model_id }}
              </option>
            </select>
          </label>

          <p v-if="fetchError" class="err">{{ fetchError }}</p>
        </div>
      </details>

      <label class="field">
        <span>接口基址</span>
        <input v-model="arkBaseUrl" type="text" :disabled="saving" />
        <small>一般无需修改；默认火山 Ark 北京区。</small>
      </label>

      <p v-if="error" class="err">{{ error }}</p>
      <p v-else-if="saved" class="ok">已保存 ✓</p>
      <p v-else-if="tested" class="ok">连接成功，可以保存了 ✓</p>
      <p v-else class="muted">改动后需先「测试连接」，连得上才能保存。</p>

      <div class="btns">
        <button class="btn" :disabled="testing || saving" @click="testConn">
          {{ testing ? "测试中…" : "测试连接" }}
        </button>
        <button class="btn btn--primary lg" :disabled="!tested || saving" @click="save">
          {{ saving ? "正在保存…" : "保存" }}
        </button>
      </div>

      <!-- ───── 在线升级 ───── -->
      <section class="update">
        <h2>版本与更新</h2>
        <div class="ver">
          <span class="muted">当前版本</span>
          <code>v{{ appVersion || "—" }}</code>
          <span class="grow" />
          <button class="btn" :disabled="updater.busy" @click="checkUpdate">
            {{ updater.phase === "checking" ? "检查中…" : "检查更新" }}
          </button>
        </div>
        <!-- 手动检查的结果反馈（横幅负责「发现新版/下载/重启」的操作，这里只给文字状态） -->
        <!-- checking 必须先于 checkedOnce 兜底分支：否则检查中会误落到「已是最新」 -->
        <p v-if="updater.phase === 'checking'" class="muted">正在检查更新…</p>
        <p v-else-if="updater.phase === 'error'" class="err">检查更新失败：{{ updater.error }}</p>
        <p v-else-if="updater.phase === 'available'" class="ok">发现新版本 v{{ updater.version }}，见顶部提示。</p>
        <p v-else-if="updater.phase === 'downloading'" class="muted">正在下载更新… {{ updater.percent }}%</p>
        <p v-else-if="updater.phase === 'ready'" class="ok">新版本已就绪，重启生效。</p>
        <p v-else-if="checkedOnce" class="ok">已是最新版本 ✓</p>
        <p v-else class="muted">应用启动时会自动检查；也可点此手动检查。</p>
      </section>
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
select {
  font-family: var(--font-body);
  font-size: 14px;
  color: var(--ink);
  background: var(--surface);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  padding: 11px 14px;
}
select:focus { outline: none; border-color: var(--amber); }
.helper {
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  background: var(--surface);
}
.link { color: var(--amber); cursor: pointer; white-space: nowrap; }
.link:hover { color: var(--amber-bright); text-decoration: underline; }
.helper > summary { font-size: 13px; color: var(--ink-dim); cursor: pointer; }
.helper > summary:hover { color: var(--amber-bright); }
.helper__body { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.helper__body .muted { font-size: 12px; line-height: 1.6; }
.creds { display: flex; gap: 10px; flex-wrap: wrap; }
.creds input { flex: 1 1 180px; }
.muted { color: var(--ink-faint); font-size: 13px; margin: 0; }
.err { color: var(--red); font-family: var(--font-mono); font-size: 13px; margin: 0; }
.ok { color: var(--amber-bright); font-size: 13px; margin: 0; }
.btns { display: flex; align-items: center; gap: 12px; }
.btn.lg { padding: 12px 24px; font-size: 14.5px; }
.update { display: flex; flex-direction: column; gap: 10px; border-top: 1px solid var(--line); padding-top: 20px; margin-top: 4px; }
.update h2 { margin: 0; font-family: var(--font-display); font-weight: 400; font-size: 18px; }
.ver { display: flex; align-items: center; gap: 10px; }
.ver code { font-family: var(--font-mono); font-size: 13px; color: var(--ink-dim); }
.ver .grow { flex: 1; }
</style>
