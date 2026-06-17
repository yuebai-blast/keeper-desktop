import { describe, it, expect } from "vitest";
import { detectOS, matchAssets, type Asset } from "./release";

describe("detectOS", () => {
  it("识别 macOS", () => {
    expect(detectOS("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit")).toBe("mac");
  });
  it("识别 Windows", () => {
    expect(detectOS("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit")).toBe("windows");
  });
  it("其它系统归为 other", () => {
    expect(detectOS("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit")).toBe("other");
  });
});

describe("matchAssets", () => {
  const assets: Asset[] = [
    { name: "Keeper_0.1.0_aarch64.dmg", browser_download_url: "u/arm.dmg" },
    { name: "Keeper_0.1.0_x64.dmg", browser_download_url: "u/intel.dmg" },
    { name: "Keeper_0.1.0_x64-setup.exe", browser_download_url: "u/win.exe" },
    { name: "Keeper_0.1.0_x64_en-US.msi", browser_download_url: "u/win.msi" },
  ];
  it("按文件名匹配三平台产物", () => {
    const m = matchAssets(assets);
    expect(m["mac-arm"]).toBe("u/arm.dmg");
    expect(m["mac-intel"]).toBe("u/intel.dmg");
    expect(m["windows"]).toBe("u/win.exe"); // exe 优先于 msi
  });
  it("缺失产物返回 null", () => {
    const m = matchAssets([]);
    expect(m["mac-arm"]).toBeNull();
    expect(m["windows"]).toBeNull();
  });
});
