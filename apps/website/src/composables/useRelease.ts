import { onMounted, ref } from "vue";
import { detectOS, matchAssets, primaryMatchKey, type Matched, type MatchKey } from "./release";

const REPO = "yuebai-blast/keeper";
export const RELEASES_LATEST = `https://github.com/${REPO}/releases/latest`;
const API = `https://api.github.com/repos/${REPO}/releases/latest`;

// 全站共享一次拉取结果（首屏与下载区复用，避免重复请求）
const version = ref<string | null>(null);
const matched = ref<Matched>({ "mac-arm": null, "mac-intel": null, windows: null });
const loading = ref(true);
const failed = ref(false);
let started = false;

async function load() {
  if (started) return;
  started = true;
  try {
    const res = await fetch(API, { headers: { Accept: "application/vnd.github+json" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    version.value = data.tag_name ?? null;
    matched.value = matchAssets(data.assets ?? []);
  } catch {
    failed.value = true; // 限流/网络失败：兜底到 Releases 页
  } finally {
    loading.value = false;
  }
}

export function useRelease() {
  onMounted(load);
  const os = detectOS(navigator.userAgent);

  // 给定匹配键返回可用下载链接：有具体产物用产物，否则回退 Releases 页
  function urlFor(key: MatchKey): string {
    return matched.value[key] ?? RELEASES_LATEST;
  }
  const primaryKey = primaryMatchKey(os);

  return { os, version, matched, loading, failed, urlFor, primaryKey, releasesLatest: RELEASES_LATEST };
}
