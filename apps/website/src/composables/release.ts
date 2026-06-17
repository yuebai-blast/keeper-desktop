// 下载逻辑纯函数：从 GitHub release 资产中按文件名匹配各平台产物，按 UA 猜系统。
// 不做副作用（fetch 在 useRelease 里），便于单测。
export type OS = "mac" | "windows" | "other";
export type MatchKey = "mac-arm" | "mac-intel" | "windows";

export interface Asset {
  name: string;
  browser_download_url: string;
}

export type Matched = Record<MatchKey, string | null>;

export function detectOS(ua: string): OS {
  if (/Windows/i.test(ua)) return "windows";
  if (/Mac OS X|Macintosh/i.test(ua)) return "mac";
  return "other";
}

export function matchAssets(assets: Asset[]): Matched {
  const find = (pred: (n: string) => boolean) =>
    assets.find((a) => pred(a.name.toLowerCase()))?.browser_download_url ?? null;

  const dmg = (n: string) => n.endsWith(".dmg");
  return {
    "mac-arm": find((n) => dmg(n) && /(aarch64|arm64)/.test(n)),
    "mac-intel": find((n) => dmg(n) && /(x64|x86_64|intel)/.test(n)),
    // exe（NSIS）优先，回退 msi
    windows: find((n) => n.endsWith(".exe")) ?? find((n) => n.endsWith(".msi")),
  };
}

// Hero 主按钮：按系统挑默认匹配键（mac 默认 Apple 芯片）
export function primaryMatchKey(os: OS): MatchKey | null {
  if (os === "mac") return "mac-arm";
  if (os === "windows") return "windows";
  return null;
}
