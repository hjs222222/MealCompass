"""Audit source introduction coverage without modifying recipe data or the database.

Run from backend/: python -m scripts.audit_recipe_durations
"""

import json
import re
from collections import Counter
from pathlib import Path

from domain.recipe_time import extract_time_text

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "recipes" / "howtocook.json"
RAW = ROOT / "data" / "raw" / "howtocook"
REPORT = ROOT / "docs" / "evidence" / "recipe_duration_audit.json"
_DURATION_WORD = re.compile(r"分钟|小时|刻钟|秒钟|天")


def audit() -> dict[str, object]:
    """Compare each imported description with the same paragraph in raw Markdown."""
    recipes: list[dict[str, object]] = json.loads(SOURCE.read_text(encoding="utf-8"))
    counters: Counter[str] = Counter()
    missing: list[dict[str, str]] = []
    samples: list[dict[str, str]] = []
    for recipe in recipes:
        name = str(recipe["name"])
        path = str(recipe["source_path"])
        description = str(recipe.get("description") or "")
        source = (RAW / path).read_text(encoding="utf-8")
        counters["recipes"] += 1
        if description not in source:
            counters["description_not_verbatim_in_raw"] += 1
        extracted = extract_time_text(description)
        if _DURATION_WORD.search(description):
            counters["description_with_duration_unit"] += 1
        if extracted:
            counters["extracted"] += 1
            if extracted not in description and not all(part in description for part in extracted.split(" ")):
                counters["extraction_not_in_source"] += 1
            if len(samples) < 8:
                samples.append({"recipe": name, "time_text": extracted, "source_path": path})
        else:
            missing.append({"recipe": name, "source_path": path, "description": description})
    return {
        "source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "raw_root": str(RAW.relative_to(ROOT)).replace("\\", "/"),
        "counts": dict(sorted(counters.items())),
        "missing_count": len(missing),
        "missing": missing,
        "examples": samples,
        "note": (
            "Duration text is display prose, not numeric total minutes; exclusions and alternatives remain in source."
        ),
    }


def main() -> None:
    report = audit()
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": report["counts"], "missing_count": report["missing_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
