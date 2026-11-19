import { describe, expect, it } from "vitest";
import { textDir } from "./textDir";

describe("textDir", () => {
  it("lays Arabic out right to left even when it opens with an English name or a figure", () => {
    expect(textDir("Marina Heights برج سكني فاخر على الواجهة البحرية")).toBe("rtl");
    expect(textDir("2026: يبدأ التسليم في الربع الثالث")).toBe("rtl");
    expect(textDir("وصف العقار")).toBe("rtl");
  });

  it("leaves English and French to the browser (left to right)", () => {
    expect(textDir("A two-bedroom apartment in Dubai Marina.")).toBe("auto");
    expect(textDir("Un appartement de deux chambres à Dubaï.")).toBe("auto");
    expect(textDir("An apartment near the مارينا promenade in Dubai")).toBe("auto");
  });

  it("is auto for anything that is not text", () => {
    expect(textDir("")).toBe("auto");
    expect(textDir(undefined)).toBe("auto");
    expect(textDir(42)).toBe("auto");
  });
});
