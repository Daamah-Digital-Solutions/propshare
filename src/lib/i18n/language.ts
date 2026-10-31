/**
 * The site's language (client, 2026-10-28): English, Arabic or French, as on Capimax BRX. The
 * choice is kept in this browser. English is what the pages are written in; Arabic and French load
 * their dictionary only when chosen, and Arabic turns the layout right-to-left. Changing
 * language reloads the page: the layer rewrites text in place, so a fresh page is the clean way.
 */

export type Language = "en" | "ar" | "fr";

export const LANGUAGES: { code: Language; label: string; name: string }[] = [
  { code: "en", label: "EN", name: "English" },
  { code: "ar", label: "AR", name: "العربية" },
  { code: "fr", label: "FR", name: "Français" },
];

const KEY = "language";

export function currentLanguage(): Language {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === "ar" || saved === "fr" ? saved : "en";
  } catch {
    return "en"; // storage blocked: the page stays in English
  }
}

export function chooseLanguage(lang: Language): void {
  if (lang === currentLanguage()) return;
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    return;
  }
  window.location.reload();
}

/** Called before the first render, so a page never flashes in English. */
export async function startLanguage(): Promise<void> {
  const lang = currentLanguage();
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  if (lang === "en") return;
  try {
    const [layer, dict] = await Promise.all([
      import("./languageLayer"),
      lang === "ar" ? import("./ar.json") : import("./fr.json"),
    ]);
    layer.enableLanguage(lang, dict.default as Record<string, string>);
  } catch {
    // the dictionary could not load: the page stays in English, and readable left-to-right
    document.documentElement.lang = "en";
    document.documentElement.dir = "ltr";
  }
}
