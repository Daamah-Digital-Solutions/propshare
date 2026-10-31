/**
 * The language layer (client, 2026-10-28): what is in the dictionary is swapped wherever it appears,
 * including text added later; names, what people type and code stay as they are; the two
 * dictionaries stay complete and keep every value a sentence takes.
 */
import { afterEach, describe, expect, it } from "vitest";
import { enableLanguage, translate } from "./languageLayer";
import ar from "./ar.json";
import fr from "./fr.json";

const DICT = {
  Wallet: "المحفظة",
  "Pay ${0}": "ادفع ${0}",
  "Paid {0} of {1}": "تم دفع {0} من {1}",
  "{0} units": "{0} وحدة",
  "Search properties...": "ابحث في العقارات...",
};

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("languageLayer", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("swaps exact text, templates, attributes and dates", () => {
    document.body.innerHTML = `<p id="a"> Wallet </p><p id="b">Paid 5 of 10</p><p id="c">Pay $20</p>
      <input id="d" placeholder="Search properties..." /><p id="e">Oct 28, 2026</p><p id="f">Oct 2026</p>`;
    enableLanguage("ar", DICT);
    expect(document.getElementById("a")!.textContent).toBe(" المحفظة ");
    expect(document.getElementById("b")!.textContent).toBe("تم دفع 5 من 10");
    expect(document.getElementById("c")!.textContent).toBe("ادفع $20");
    expect(document.getElementById("d")!.getAttribute("placeholder")).toBe("ابحث في العقارات...");
    expect(document.getElementById("e")!.textContent).toBe("28 أكتوبر 2026");
    expect(document.getElementById("f")!.textContent).toBe("أكتوبر 2026");
  });

  it("French has its own months, with the time when there is one", () => {
    document.body.innerHTML = `<p id="a">Oct 28, 2026, 4:07 PM</p>`;
    enableLanguage("fr", {});
    expect(document.getElementById("a")!.textContent).toBe("28 oct. 2026 à 4:07 PM");
  });

  it("covers what appears later and what React changes", async () => {
    document.body.innerHTML = `<div id="root"><span id="s">Marina Loft</span></div>`;
    enableLanguage("ar", DICT);
    const added = document.createElement("p");
    added.textContent = "Wallet";
    document.getElementById("root")!.appendChild(added);
    await tick();
    expect(added.textContent).toBe("المحفظة");
    document.getElementById("s")!.firstChild!.nodeValue = "12 units";
    await tick();
    expect(document.getElementById("s")!.textContent).toBe("12 وحدة");
  });

  it("leaves names, typed text and marked content as written", () => {
    document.body.innerHTML = `<p id="a">Marina Loft</p><p id="b" translate="no">Wallet</p>
      <code id="c">Wallet</code><textarea id="d">Wallet</textarea>`;
    enableLanguage("ar", DICT);
    expect(document.getElementById("a")!.textContent).toBe("Marina Loft");
    expect(document.getElementById("b")!.textContent).toBe("Wallet");
    expect(document.getElementById("c")!.textContent).toBe("Wallet");
    expect((document.getElementById("d") as HTMLTextAreaElement).value).toBe("Wallet");
    expect(translate("Marina Loft")).toBeNull();
  });

  it("an English plural ending never reaches the other language", () => {
    enableLanguage("ar", { "{0} unit{1} of {2}": "{0} وحدة{1} من {2}" });
    expect(translate("3 units of Marina")).toBe("3 وحدة من Marina");
    enableLanguage("fr", { "{0} unit{1} of {2}": "{0} unité{1} de {2}" });
    expect(translate("3 units of Marina")).toBe("3 unités de Marina");
    expect(translate("1 unit of Marina")).toBe("1 unité de Marina");
  });

  it("a template with no words of its own never matches", () => {
    enableLanguage("ar", { "{0} / {1}": "{1} / {0}" });
    expect(translate("Marina / Loft")).toBeNull();
  });
});

describe("the dictionaries", () => {
  const placeholders = (s: string) => (s.match(/\{\d+\}/g) ?? []).sort().join();

  it.each([
    ["ar", ar as Record<string, string>],
    ["fr", fr as Record<string, string>],
  ])("%s keeps every value of each sentence", (_lang, dict) => {
    const wrong = Object.entries(dict).filter(([en, out]) => placeholders(en) !== placeholders(out));
    expect(wrong).toEqual([]);
  });

  it("Arabic is Arabic: a full sentence is never left in English", () => {
    const left = Object.entries(ar as Record<string, string>).filter(
      ([en, out]) => en.split(" ").length > 3 && !/[؀-ۿ]/.test(out),
    );
    expect(left.map(([en]) => en)).toEqual([]);
  });

  it("the same strings in both languages", () => {
    expect(Object.keys(ar).length).toBe(Object.keys(fr).length);
  });
});
