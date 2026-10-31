/**
 * Arabic and French for the whole interface without touching every page (client, 2026-10-28; the
 * same approach as Capimax BRX's French layer).
 *
 * The pages are written in English. This layer swaps that English as it appears, from one
 * dictionary per language (ar.json, fr.json; scripts/i18n_extract.py lists every string, and
 * scripts/i18n_check.py reports any without a translation):
 *  - exact sentences ("Pay from Balance"),
 *  - templates for sentences built with values ("Paid {0} of {1}"),
 *  - dates the pages format in English ("Oct 28, 2026").
 * It covers text and the placeholder / title / aria-label / alt attributes, including dialogs
 * opened later (a MutationObserver). It leaves alone anything marked translate="no", what people
 * type, code, and whatever is not in the dictionary, so a property's or a person's name stays
 * as written.
 *
 * Changing language reloads the page (language.ts), so nothing has to be swapped back. English
 * never loads this file.
 */

export type LayerLanguage = "ar" | "fr";

type Template = { re: RegExp; out: string; plurals: Set<number> };

const ATTRS = ["placeholder", "title", "aria-label", "alt"] as const;
const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "CODE", "PRE", "TEXTAREA", "INPUT"]);

const MONTH_NAMES: Record<LayerLanguage, string[]> = {
  ar: ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"],
  fr: ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
};
const AT: Record<LayerLanguage, string> = { ar: "الساعة", fr: "à" };
const MONTHS_RE = [
  "Jan(?:uary)?", "Feb(?:ruary)?", "Mar(?:ch)?", "Apr(?:il)?", "May", "June?", "July?", "Aug(?:ust)?",
  "Sep(?:t(?:ember)?)?", "Oct(?:ober)?", "Nov(?:ember)?", "Dec(?:ember)?",
];
const MONTH = `(${MONTHS_RE.join("|")})\\.?`;
const LONE_MONTHS = MONTHS_RE.map((m) => new RegExp(`^(?:${m})\\.?$`));

let language: LayerLanguage = "fr";
let exact = new Map<string, string>();
let templates: Template[] = [];
const misses = new Set<string>();
// What this layer last wrote, so its own writes are not translated again.
const written = new WeakMap<Node, string>();
let observer: MutationObserver | null = null;

const norm = (s: string) => s.replace(/\s+/g, " ").trim();
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function build(dict: Record<string, string>) {
  exact = new Map();
  templates = [];
  for (const [en, out] of Object.entries(dict)) {
    if (!out) continue;
    if (/\{\d+\}/.test(en)) {
      // a template with no words of its own ("{0} / {1}") would match anything
      if (!/[A-Za-z]/.test(en.replace(/\{\d+\}/g, ""))) continue;
      const order: number[] = [];
      const plurals = new Set<number>();
      const source = escapeRe(en).replace(/(\w?)\\\{(\d+)\\\}/g, (_m, before, n) => {
        order.push(Number(n));
        // "unit{1}": an English plural ending, right after a letter
        if (/[A-Za-z]/.test(before)) {
          plurals.add(order.length - 1);
          return `${before}(s?)`;
        }
        return `${before}(.+?)`;
      });
      templates.push({
        re: new RegExp(`^${source}$`),
        out: out.replace(/\{(\d+)\}/g, (_m, n) => `{${order.indexOf(Number(n))}}`),
        plurals,
      });
    } else {
      exact.set(norm(en), out);
    }
  }
  // Longer (more specific) templates first.
  templates.sort((a, b) => b.re.source.length - a.re.source.length);
}

const monthName = (m: string) => {
  const i = LONE_MONTHS.findIndex((re) => re.test(m));
  return i < 0 ? m : MONTH_NAMES[language][i];
};

/** The text with its English dates in this language; the same text if it has none. */
function dates(text: string): string {
  if (LONE_MONTHS.some((re) => re.test(text))) return monthName(text); // "Jan" on a chart
  return text
    .replace(new RegExp(`\\b${MONTH} (\\d{1,2}),? (\\d{4})(?:(?:,| at) (\\d{1,2}:\\d{2}(?: ?[AP]M)?))?`, "g"),
      (_m, mo, d, y, time) => `${d} ${monthName(mo)} ${y}${time ? ` ${AT[language]} ${time}` : ""}`)
    .replace(new RegExp(`\\b(\\d{1,2}) ${MONTH} (\\d{4})\\b`, "g"), (_m, d, mo, y) => `${d} ${monthName(mo)} ${y}`)
    .replace(new RegExp(`\\b${MONTH} '?(\\d{4})\\b`, "g"), (_m, mo, y) => `${monthName(mo)} ${y}`);
}

/** This language for one piece of English text, keeping its surrounding spaces; null if unknown. */
export function translate(text: string): string | null {
  const key = norm(text);
  if (!key || !/[A-Za-z]/.test(key) || misses.has(key)) return null;
  let out = exact.get(key);
  if (out === undefined) {
    for (const t of templates) {
      const m = key.match(t.re);
      if (m) {
        // A filled-in value that is itself known text is translated too.
        out = t.out.replace(/\{(\d+)\}/g, (_x, i) => {
          const value = m[Number(i) + 1] ?? "";
          if (t.plurals.has(Number(i))) return language === "ar" ? "" : value;
          return (value !== key && translate(value)) || value;
        });
        break;
      }
    }
  }
  if (out === undefined) {
    const dated = dates(key);
    if (dated !== key) out = dated;
  }
  if (out === undefined) {
    misses.add(key);
    return null;
  }
  const lead = text.match(/^\s*/)?.[0] ?? "";
  const trail = text.match(/\s*$/)?.[0] ?? "";
  return lead + out + trail;
}

function skipped(el: Element | null): boolean {
  for (let e = el; e; e = e.parentElement) {
    if (SKIP_TAGS.has(e.tagName)) return true;
    if (e.getAttribute("translate") === "no" || e.classList.contains("notranslate")) return true;
    if ((e as HTMLElement).isContentEditable) return true;
  }
  return false;
}

function textNode(node: Text) {
  const value = node.nodeValue ?? "";
  if (written.get(node) === value || skipped(node.parentElement)) return;
  const out = translate(value);
  if (out !== null && out !== value) {
    written.set(node, out);
    node.nodeValue = out;
  }
}

function attributes(el: Element) {
  // a field's placeholder and label are ours; what is typed in it is a value, never touched
  const field = el.tagName === "INPUT" || el.tagName === "TEXTAREA";
  if (skipped(field ? el.parentElement : el) || el.getAttribute("translate") === "no") return;
  for (const name of ATTRS) {
    const value = el.getAttribute(name);
    if (!value) continue;
    const out = translate(value);
    if (out !== null && out !== value) el.setAttribute(name, out);
  }
}

function walk(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) {
    textNode(root as Text);
    return;
  }
  if (root.nodeType !== Node.ELEMENT_NODE) return;
  const el = root as Element;
  attributes(el);
  const it = document.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  for (let n = it.nextNode(); n; n = it.nextNode()) {
    if (n.nodeType === Node.TEXT_NODE) textNode(n as Text);
    else attributes(n as Element);
  }
}

/** Turn this language on for the whole document (idempotent). */
export function enableLanguage(lang: LayerLanguage, dict: Record<string, string>) {
  language = lang;
  build(dict);
  misses.clear();
  // while developing: every text with no translation, to read in the console
  if (import.meta.env.DEV) (window as unknown as { __i18nMisses: Set<string> }).__i18nMisses = misses;
  walk(document.body);
  observer?.disconnect();
  observer = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === "characterData") textNode(m.target as Text);
      else if (m.type === "attributes") attributes(m.target as Element);
      else m.addedNodes.forEach(walk);
    }
  });
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: [...ATTRS],
  });
}
