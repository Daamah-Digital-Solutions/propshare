"""
Report every English string that has no Arabic or French yet.

  python scripts/i18n_check.py            # list what is missing; exit 1 if anything is
  python scripts/i18n_check.py --write X  # also write the missing strings to X (JSON)

Run after changing interface text: a new English sentence shows in English to Arabic and French
readers until it is added to src/lib/i18n/ar.json and fr.json.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from i18n_extract import ui_strings  # noqa: E402

HERE = os.path.join(os.path.dirname(__file__), "..", "src", "lib", "i18n")


def load(name):
    return json.load(io.open(os.path.join(HERE, name), encoding="utf-8"))


def main():
    ui = ui_strings()
    missing = set()
    bad = []
    for lang in ("ar", "fr"):
        d = load(f"{lang}.json")
        gone = [s for s in ui if not d.get(s)]
        missing.update(gone)
        for en, out in d.items():
            if set(re.findall(r"\{\d+\}", en)) != set(re.findall(r"\{\d+\}", out or "")):
                bad.append(f"{lang}: {en}")
        print(f"{lang}: {len(ui) - len(gone)}/{len(ui)} translated")
    print(f"placeholder mismatches: {len(bad)}")
    for s in sorted(missing)[:30] + bad[:30]:
        print("  -", s[:110])
    if "--write" in sys.argv:
        path = sys.argv[sys.argv.index("--write") + 1]
        json.dump(sorted(missing), io.open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return 1 if missing or bad else 0


if __name__ == "__main__":
    sys.exit(main())
