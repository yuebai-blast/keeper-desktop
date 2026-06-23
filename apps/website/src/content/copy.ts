// 全站文案：中英两份，结构必须一致。组件只从这里取文案，不内联硬编码。
export interface DownloadItem {
  os: string;       // 平台名
  arch: string;     // 芯片/架构说明
  ext: string;      // 产物格式
  match: "mac-arm" | "windows"; // 与 release 资产匹配键
}

export interface Copy {
  nav: { download: string; how: string; features: string; faq: string; github: string };
  hero: {
    kicker: string; titleA: string; titleB: string; lede: string;
    primaryPrefix: string; otherPlatforms: string;
    detecting: string; fallbackPrimary: string; meta: string;
    wallBadge: string; keep: string; cut: string; polaroidCap: string;
  };
  principles: { kicker: string; title: string; items: { title: string; body: string; tone: "green" | "red" }[] };
  how: { kicker: string; title: string; lede: string; steps: { n: string; title: string; body: string }[] };
  features: { kicker: string; title: string; items: { title: string; body: string }[] };
  showcase: { kicker: string; title: string; lede: string; reqTitle: string; reqs: string[]; shotAlt: string[] };
  download: {
    kicker: string; title: string; lede: string;
    items: DownloadItem[]; button: string;
    unsignedTitle: string; macUnsigned: string; winUnsigned: string;
  };
  faq: { kicker: string; title: string; items: { q: string; a: string }[] };
  footer: { tagline: string; download: string; github: string; docs: string; license: string; copyright: string };
}

const zh: Copy = {
  nav: { download: "下载", how: "工作流", features: "特性", faq: "常见问题", github: "GitHub" },
  hero: {
    kicker: "本地优先 · AI 选片",
    titleA: "把最好的留下",
    titleB: "留在你自己的电脑里",
    lede: "相似连拍自动归组，两层级联漏斗为每组递上候选——照片不出本地，机器不替你做最终淘汰。留谁，你在 A/B 擂台上说了算。",
    primaryPrefix: "下载 Keeper · ",
    otherPlatforms: "其它平台",
    detecting: "正在识别系统…",
    fallbackPrimary: "前往下载",
    meta: "免费 · 支持 macOS / Windows",
    wallBadge: "9 张 → 留 2 张",
    keep: "留", cut: "舍", polaroidCap: "the keeper",
  },
  principles: {
    kicker: "两条原则", title: "我们坚持的两件事",
    items: [
      { title: "照片不出本地", body: "原图永远只在你的电脑上被读取；仅用于打分的低清预览会临时上云、用完即焚。", tone: "green" },
      { title: "机器不替你做最终淘汰", body: "机器只负责为每组递上一份足够好的候选；留谁、是否整组舍弃，是你在擂台上的权利。", tone: "red" },
    ],
  },
  how: {
    kicker: "工作流", title: "四步，从一堆连拍到精选", lede: "每层漏斗规则相同：≥60 分全进下一层，不足保底数则按分补够，绝不替你砍掉够好的。",
    steps: [
      { n: "01", title: "分组", body: "相似连拍按语义 + 时间 + 人脸自动聚成「同一个瞬间」。" },
      { n: "02", title: "本地初筛", body: "在你电脑上按技术质量打分：锐度 / 曝光 / 人脸 / 美学，闭眼脱焦扣分。" },
      { n: "03", title: "AI 精评", body: "联网用 AI 按审美 / 表情 / 构图 / 语义打分，给出可解释的去留理由。" },
      { n: "04", title: "A/B 擂台终选", body: "你在擂台上两两对决，做最终裁决——留谁你说了算。" },
    ],
  },
  features: {
    kicker: "特性", title: "为什么是 Keeper",
    items: [
      { title: "本地模型评分", body: "画质 / 美学 / 人脸等多个本地 AI 模型在你机器上跑，离线可用。" },
      { title: "在线大模型审美", body: "接火山方舟（Ark），按审美与语义二次精选。" },
      { title: "RAW · HEIC 支持", body: "原生解码主流相机 RAW 与 HEIC，缩略图就近缓存。" },
      { title: "人脸归组", body: "同场景不同人自动拆开，多人合影按「是不是同一拨人」区分。" },
      { title: "可解释去留", body: "每张照片给出留下/舍弃的理由，不是黑箱。" },
      { title: "项目可恢复", body: "选片以项目为单位，每步持久化，随时退出、稍后继续。" },
    ],
  },
  showcase: {
    kicker: "界面一览", title: "为选片而生的暗房界面", lede: "和官网同一套设计语言——暖调深色、克制、让照片发光。",
    reqTitle: "系统要求",
    reqs: [
      "macOS 11+（Apple 芯片）或 Windows 10+（x64）",
      "首次启动联网，一次性下载约 1.6 GB 本地 AI 模型到 ~/.keeper/models，之后完全离线",
      "AI 精评需自备火山方舟（Ark）API key（可在应用内录入）",
    ],
    shotAlt: ["组详情：本地 + AI 评分与去留", "A/B 擂台：两两对决终选"],
  },
  download: {
    kicker: "下载", title: "选择你的平台", lede: "免费下载，安装包托管在 GitHub Releases。",
    items: [
      { os: "macOS · Apple 芯片", arch: "M 系列（aarch64）", ext: ".dmg", match: "mac-arm" },
      { os: "Windows", arch: "x64", ext: ".exe / .msi", match: "windows" },
    ],
    button: "下载",
    unsignedTitle: "首次打开需手动放行（当前未做代码签名）",
    macUnsigned: "macOS：若提示「已损坏」或「无法验证开发者」，到「系统设置 → 隐私与安全性」点「仍要打开」；或终端执行 xattr -dr com.apple.quarantine /Applications/Keeper.app",
    winUnsigned: "Windows：SmartScreen 拦截时点「更多信息 → 仍要运行」。",
  },
  faq: {
    kicker: "常见问题", title: "你可能想问",
    items: [
      { q: "Keeper 免费吗？", a: "当前 MVP 版本免费。商业版的云端中转/计费是后续计划。" },
      { q: "我的照片会被上传吗？", a: "原图永远不离开你的电脑。只有用于大模型打分的低清预览会临时上传、用完即焚；拍摄地反查只发 GPS 坐标。" },
      { q: "需要联网吗？", a: "首次启动需联网下载本地模型（约 1.6 GB）。之后本地流程完全离线；只有 AI 精评需要联网。" },
      { q: "未签名安装包怎么放行？", a: "macOS 到「隐私与安全性」点「仍要打开」，或用 xattr 去隔离属性；Windows 在 SmartScreen 点「仍要运行」。" },
      { q: "需要 API key 吗？", a: "AI 精评需要火山方舟（Ark）API key，在应用「设置」页录入，密钥只存本地、绝不入库。" },
      { q: "可以商用吗？", a: "当前内置的人脸识别模型仅供非商用研究，商用前需替换或获授权。" },
    ],
  },
  footer: {
    tagline: "把最好的留下，留在你自己的电脑里。",
    download: "下载", github: "GitHub", docs: "文档",
    license: "内置人脸识别模型仅供非商用研究。",
    copyright: "© 2026 Keeper · 留影",
  },
};

const en: Copy = {
  nav: { download: "Download", how: "How it works", features: "Features", faq: "FAQ", github: "GitHub" },
  hero: {
    kicker: "Local-first · AI culling",
    titleA: "Keep the best,",
    titleB: "on your own machine",
    lede: "Burst shots are grouped automatically; a two-stage funnel hands you the candidates. Photos never leave your machine, and the machine never makes the final cut — you do, in the A/B arena.",
    primaryPrefix: "Download Keeper · ",
    otherPlatforms: "Other platforms",
    detecting: "Detecting your OS…",
    fallbackPrimary: "Go to downloads",
    meta: "Free · macOS / Windows",
    wallBadge: "9 shots → keep 2",
    keep: "keep", cut: "cut", polaroidCap: "the keeper",
  },
  principles: {
    kicker: "Two principles", title: "Two things we won't bend on",
    items: [
      { title: "Photos stay local", body: "Originals are only ever read on your machine; only low-res previews for scoring go to the cloud — used once, then discarded.", tone: "green" },
      { title: "You make the final cut", body: "The machine only hands each group a good-enough shortlist. What to keep, or whether to drop the whole group, is your call.", tone: "red" },
    ],
  },
  how: {
    kicker: "How it works", title: "Four steps, from bursts to picks", lede: "Each funnel uses the same rule: everything ≥60 passes; if short of the quota, top up by score — never cutting anything good enough.",
    steps: [
      { n: "01", title: "Group", body: "Similar bursts are clustered into one 'moment' by semantics, time and faces." },
      { n: "02", title: "Local pre-screen", body: "On your machine: technical scoring — sharpness, exposure, faces, aesthetics; penalties for closed eyes / out-of-focus." },
      { n: "03", title: "AI review", body: "Online AI scores aesthetics, expression, composition and semantics, with explainable keep/cut reasons." },
      { n: "04", title: "A/B arena", body: "You decide head-to-head in the arena — the final cut is always yours." },
    ],
  },
  features: {
    kicker: "Features", title: "Why Keeper",
    items: [
      { title: "Local model scoring", body: "Several local AI models (quality / aesthetics / faces) run on your machine, offline-capable." },
      { title: "Cloud LLM aesthetics", body: "Volcano Ark for a second, taste-aware pass." },
      { title: "RAW · HEIC support", body: "Native decoding of common camera RAW and HEIC, with thumbnail caching." },
      { title: "Face-aware grouping", body: "Same scene, different people get split apart; group photos by 'same crew or not'." },
      { title: "Explainable picks", body: "Every photo gets a keep/cut reason — not a black box." },
      { title: "Resumable projects", body: "Culling is project-based; every step is persisted, quit and resume anytime." },
    ],
  },
  showcase: {
    kicker: "A look inside", title: "A darkroom built for culling", lede: "Same design language as this site — warm, dark, restrained, letting photos glow.",
    reqTitle: "Requirements",
    reqs: [
      "macOS 11+ (Apple Silicon) or Windows 10+ (x64)",
      "First launch downloads ~1.6 GB of local AI models to ~/.keeper/models, then runs fully offline",
      "AI review needs your own Volcano Ark API key (entered in-app)",
    ],
    shotAlt: ["Group detail: local + AI scores and verdicts", "A/B arena: head-to-head final pick"],
  },
  download: {
    kicker: "Download", title: "Pick your platform", lede: "Free download, installers hosted on GitHub Releases.",
    items: [
      { os: "macOS · Apple Silicon", arch: "M-series (aarch64)", ext: ".dmg", match: "mac-arm" },
      { os: "Windows", arch: "x64", ext: ".exe / .msi", match: "windows" },
    ],
    button: "Download",
    unsignedTitle: "First open needs manual approval (currently unsigned)",
    macUnsigned: "macOS: if it says 'damaged' or 'unverified developer', go to System Settings → Privacy & Security and click 'Open Anyway'; or run xattr -dr com.apple.quarantine /Applications/Keeper.app",
    winUnsigned: "Windows: when SmartScreen blocks it, click 'More info → Run anyway'.",
  },
  faq: {
    kicker: "FAQ", title: "You might be wondering",
    items: [
      { q: "Is Keeper free?", a: "The current MVP is free. A commercial cloud-relay/billing version is planned." },
      { q: "Are my photos uploaded?", a: "Originals never leave your machine. Only low-res previews for LLM scoring are uploaded then discarded; geocoding sends GPS coordinates only." },
      { q: "Do I need internet?", a: "First launch downloads local models (~1.6 GB). After that the local pipeline is fully offline; only the AI review needs the network." },
      { q: "How do I open an unsigned build?", a: "macOS: 'Open Anyway' in Privacy & Security, or strip the quarantine attr with xattr. Windows: 'Run anyway' in SmartScreen." },
      { q: "Do I need an API key?", a: "The AI review needs a Volcano Ark API key, entered in Settings; it's stored locally and never committed." },
      { q: "Can I use it commercially?", a: "The bundled face-recognition model is for non-commercial research only; replace or license it before commercial use." },
    ],
  },
  footer: {
    tagline: "Keep the best, on your own machine.",
    download: "Download", github: "GitHub", docs: "Docs",
    license: "Bundled face-recognition model is for non-commercial research only.",
    copyright: "© 2026 Keeper",
  },
};

export const COPY: Record<"zh" | "en", Copy> = { zh, en };
