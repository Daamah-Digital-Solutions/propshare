"""
Extract every English string the language layer must know (src/lib/i18n/languageLayer.ts).

  python scripts/i18n_extract.py [out_dir]

Writes ui_en.json: every English text the pages render: JSX text, sentence literals, and
placeholder / title / aria-label attributes. A text built with ${...} becomes a template:
"Paid {0} of {1}". src/lib/i18n/ar.json and fr.json must hold a line for each entry
(scripts/i18n_check.py reports what is missing).
"""
import html
import io
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "src")
STR = r'''(?P<q>["'`])(?P<s>(?:\\.|(?!(?P=q)).)*?)(?P=q)'''


def unescape(s: str) -> str:
    return (s.replace("\\'", "'").replace('\\"', '"').replace("\\`", "`")
            .replace("\\n", "\n").replace("\\\\", "\\"))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def template(s: str) -> str:
    """`Paid ${a} of ${b}` → "Paid {0} of {1}"."""
    i = -1

    def rep(_m):
        nonlocal i
        i += 1
        return "{%d}" % i

    return re.sub(r"\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", rep, s)


CSSISH = re.compile(r"^[a-z0-9\-:/\[\]\.%#_ ()!,=>&]+$")
CODEISH = re.compile(
    # code words only in code shape, so "rate of return" / "null and void" stay text
    r"[{}]|;\s*(?:const|let|var|return|if|\}|\)|$)|=>|===|!==|&&|\|\||\bconst\s+\w+\s*=|\buse[A-Z]\w*|\breturn\s*[(<;\[]"
    r"|\(\)|[=(,:]\s*null\b|\bnull\s*[;),]|;\s*case\b|\bdefault:\s*return"
)


def is_ui_text(s: str, paired: bool = False) -> bool:
    """paired: the English side of an Arabic/English pair, so a lower-case word ("units") is text too."""
    s = norm(s)
    if paired and re.fullmatch(r"[a-z][a-z'’]*[.!?:]?", s):
        return s not in {"en", "ar", "ltr", "rtl", "r", "left", "right"}  # language / direction codes, css sides
    if not s or not re.search(r"[A-Za-z]", s):
        return False
    if re.match(r"^[MmLlCcHhVvZz]\s*-?[\d.]", s) or re.fullmatch(r"[dMyHhms ,:/.\-]+", s):
        return False  # an SVG path or a date-format pattern, never shown as text
    if re.match(r"^(else|if|return|const|let|await|case|import|from|type|interface|function)\b", s) or re.search(r"[(]\w*[)]$|\w\.\w+\(|\b(as|in) const\b", s):
        return False  # code around a JSX expression
    if CODEISH.search(re.sub(r"\{\d+\}", "", s)):
        return False  # a TypeScript fragment the JSX-text pattern caught (generics etc.)
    if s.startswith(("http", "/", "#", "./", "@/", "mailto:", "tel:")) or s.endswith((".tsx", ".ts", ".png", ".svg")):
        return False
    if " " not in s:
        # one word: keep Capitalised words ("Deposit"), drop identifiers / css / keys
        return bool(re.fullmatch(r"[A-Z][a-zA-Z'’]*[.!?:]?", s)) or s in {"e.g."}
    if CSSISH.match(s) and ("-" in s or ":" in s):
        return False  # tailwind classes
    return True


def concat_strings(expr: str) -> str | None:
    """'"a " + "b"' → "a b" (only plain literals)."""
    parts = re.findall(r'''(["'])((?:\\.|(?!\1).)*)\1''', expr)
    rest = re.sub(r'''(["'])((?:\\.|(?!\1).)*)\1''', "", expr)
    if re.sub(r"[\s+]", "", rest):
        return None
    return "".join(unescape(p[1]) for p in parts)


# what the code picks by value, or reads out of data: no pattern can see these
EXTRA = [
    "unread", "unit", "units", "file", "document", "deposit", "transfer", "withdrawal", "investment",
    "return", "fee", "gift", "Cancelled by you.", "All my certificates (ZIP)", "Certificate (PDF)",
]
PY_STR = r"""f?(?:"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')"""
PY_CHAIN = r"((?:\s*" + PY_STR + r")+)"
PY_PIECE = re.compile(r"""f?(?:"((?:\\.|[^"\\\n])*)"|'((?:\\.|[^'\\\n])*)')""")


def py_text(chain: str) -> str:
    text = "".join(a or b for a, b in PY_PIECE.findall(chain))
    i = -1

    def rep(_m):
        nonlocal i
        i += 1
        return "{%d}" % i

    return re.sub(r"\{[^{}]*\}", rep, unescape(text))


def server_strings():
    """English the API sends and the pages show as is: AppError messages, notification titles
    and messages, descriptions, labels. An f-string becomes a template."""
    out = set(EXTRA)
    backend = os.path.join(ROOT, "..", "backend", "app")
    err = re.compile(r"""AppError\(\s*["'][A-Z_0-9]+["']\s*,""" + PY_CHAIN)
    named = re.compile(r"\b(?:title|message|description|label|email_subject)\s*=\s*\(?" + PY_CHAIN)
    item = re.compile(r"""^\s*"[a-z_]+":\s*"([A-Z][^"\n]*)",\s*$""", re.M)
    for dirpath, _dirs, files in os.walk(backend):
        if any(x in dirpath for x in ("tests", "knowledge", "__pycache__", "assistant", "llm", "alembic")):
            continue
        for fn in files:
            if not fn.endswith(".py") or fn.startswith("admin"):
                continue
            src = io.open(os.path.join(dirpath, fn), encoding="utf-8").read()
            for rx in (err, named):
                for m in rx.finditer(src):
                    out.add(py_text(m.group(1)))
            if fn.endswith("_service.py"):
                out.update(item.findall(src))
    return out


def ui_strings():
    found = set()
    paired = set()  # strings that are the English side of an Arabic/English pair
    ternary = re.compile(
        r"(?:isArabic|isAr|isRTL|\bar|language\s*===\s*[\"']ar[\"'])\s*\?\s*" + STR.replace("q>", "q1>").replace("s>", "a>").replace("(?P=q)", "(?P=q1)")
        + r"\s*:\s*" + STR, re.S)
    field = re.compile(r"\b(?:en|[a-z]+En)\s*:\s*((?:" + r'''(["'])(?:\\.|(?!\2).)*\2''' + r"\s*\+?\s*)+)", re.S)
    lcall = re.compile(r"\bL\(\s*" + STR + r"\s*,", re.S)
    jsx_text = re.compile(r"[>}]\s*([^<>{}=;]*[A-Za-z][^<>{}=;]*?)\s*(?=[<{])")
    jsx_after_tag = re.compile(r">\s*([^<>{}]*[A-Za-z][^<>{}]*?)\s*(?=[<{])")
    # "a sentence with an apostrophe's" and sentences split with + over several lines
    dq_sentence = re.compile(r'"([A-Z][^"\n]*? [^"\n]*?)"')
    plus_chain = re.compile(r'((?:"(?:\\.|[^"\\\n])*"\s*\+\s*)+"(?:\\.|[^"\\\n])*")')
    # a one-word label literal ("Pending", label: "Wallet"): not a className, not an import
    one_word = re.compile(r"""(?<![\w=])(["'])([A-Z][a-z]+(?:[-'][A-Za-z]+)?)\1""")
    # a template literal with words in it: `Paid ${a} of ${b}`
    backtick = re.compile(r"`((?:\\.|[^`\\])*)`")
    # `isAr ? ["…", …] : ["…", …]` — every string of the English list
    arr_ternary = re.compile(
        r"(?:isArabic|isAr|isRTL|language\s*===\s*[\"']ar[\"'])\s*\?\s*\[[^\[\]]*\]\s*:\s*\[([^\[\]]*)\]", re.S)
    # any English sentence literal ("Something with spaces"): English-only text, toasts, labels
    sentence = re.compile(r"""(["'])([A-Z][^"'\n]*? [^"'\n]*?)\1""")
    quoted = re.compile(r"""(["'])((?:\\.|(?!\1).)*)\1""")
    # any helper called as f("English", "عربي") — the English argument
    en_ar_call = re.compile(r"\(\s*" + STR + r"""\s*,\s*["'][^"'\n]*[؀-ۿ]""")
    attr = re.compile(r"\b(?:placeholder|title|aria-label|alt|label)=\"([^\"]*[A-Za-z][^\"]*)\"")
    # `en: \`Receipt — ${title}\`` — a template field
    bt_field = re.compile(r"\b(?:en|[a-z]+En)\s*:\s*`((?:\\.|[^`\\])*)`")
    # Labels the server sends in English (wallet ledger sources, payment providers)
    for dirpath, _dirs, files in os.walk(ROOT):
        for fn in files:
            if not fn.endswith((".tsx", ".ts")) or fn.endswith((".test.tsx", ".test.ts", ".d.ts")):
                continue
            path = os.path.join(dirpath, fn)
            if os.path.join("lib", "i18n") in path or os.sep + "test" + os.sep in path:
                continue
            src = io.open(path, encoding="utf-8").read()
            for m in ternary.finditer(src):
                s = template(unescape(m.group("s"))) if m.group("q") == "`" else unescape(m.group("s"))
                found.add(s)
                paired.add(s)
            for m in field.finditer(src):
                if re.search(r"\bnameEn\s*:", m.group(0)):
                    continue  # names (properties, partners) stay as written
                val = concat_strings(m.group(1))
                if val:
                    found.add(val)
            for m in bt_field.finditer(src):
                if not re.search(r"\bnameEn\s*:", m.group(0)):
                    found.add(template(unescape(m.group(1))))
            for m in lcall.finditer(src):
                found.add(unescape(m.group("s")))
            for m in en_ar_call.finditer(src):
                found.add(unescape(m.group("s")))
                paired.add(unescape(m.group("s")))
            for m in arr_ternary.finditer(src):
                for q in quoted.findall(m.group(1)):
                    found.add(unescape(q[1]))
            for line in src.splitlines():
                if re.match(r"\s*(import|export \* from)\b", line) or "console." in line:
                    continue
                for m in sentence.finditer(line):
                    if not re.search(r"[؀-ۿ]", m.group(2)):
                        found.add(unescape(m.group(2)))
                if "className" not in line and "queryKey" not in line and "type:" not in line:
                    for m in one_word.finditer(line):
                        found.add(m.group(2))
            for m in dq_sentence.finditer(src):
                found.add(unescape(m.group(1)))
            for m in plus_chain.finditer(src):
                found.add(unescape("".join(re.findall(r'"((?:\\.|[^"\\\n])*)"', m.group(1)))))
            for m in backtick.finditer(src):
                t = template(unescape(m.group(1)))
                bare = re.sub(r"\{\d+\}", "", t)
                # words, not a path, a class list or a query string
                if re.search(r"[A-Za-z]{2,}", bare) and " " in t and not re.search(r"[/=&?]\S|\$\{|-\d|\bpx\b|^[a-z-]+ [a-z-]+", bare.strip()):
                    found.add(t)
            if fn.endswith(".tsx"):
                for rx in (jsx_text, jsx_after_tag):
                    for m in rx.finditer(src):
                        found.add(html.unescape(m.group(1)))
                for m in attr.finditer(src):
                    found.add(m.group(1))
    found |= server_strings()
    # code the patterns catch and proper names: checked once, kept out of the dictionaries
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n_ignore.json")
    ignore = set(json.load(io.open(path, encoding="utf-8"))) if os.path.exists(path) else set()
    paired |= set(EXTRA)
    out = {norm(s) for s in found if is_ui_text(s, s in paired)} - ignore
    return sorted(out)


if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out_dir, exist_ok=True)
    ui = ui_strings()
    json.dump(ui, io.open(os.path.join(out_dir, "ui_en.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"ui strings: {len(ui)}  templates: {sum('{0}' in s for s in ui)}")
