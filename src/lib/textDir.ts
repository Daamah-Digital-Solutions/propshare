// The direction of a piece of a listing's own text (client, 2026-11-19: "Arabic must read from the
// right"). dir="auto" takes the direction of the first letter, so an Arabic paragraph that opens
// with an English name or a figure (a tower's English name, then its Arabic description) was laid
// out left to right.
// Here the letters decide: mostly Arabic is right to left; anything else keeps dir="auto" (English
// or French shown on the Arabic site as the fallback still reads left to right).

// Hebrew, Arabic and their presentation forms (written as escapes: the range ends are invisible)
const RTL_LETTERS = new RegExp("[\\u0590-\\u08FF\\uFB1D-\\uFDFF\\uFE70-\\uFEFC]", "g");
const LATIN_LETTERS = new RegExp("[A-Za-z\\u00C0-\\u024F]", "g");

export function textDir(text: unknown): "rtl" | "auto" {
  if (typeof text !== "string" || !text) return "auto";
  const rtl = text.match(RTL_LETTERS)?.length ?? 0;
  if (!rtl) return "auto";
  const latin = text.match(LATIN_LETTERS)?.length ?? 0;
  return rtl >= latin ? "rtl" : "auto";
}
