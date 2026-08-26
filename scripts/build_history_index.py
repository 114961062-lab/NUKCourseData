#!/usr/bin/env python3
"""彙整data/history內各學年度metadata，產生歷史資料索引。"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = Path(
    os.getenv("NUK_HISTORY_DIR", str(ROOT / "data" / "history"))
).resolve()
INDEX_FILE = HISTORY_DIR / "index.json"


def main() -> int:
    years = []
    terms = []
    total_courses = 0

    for path in sorted(HISTORY_DIR.glob("nuk_courses_*_metadata.json")):
        with path.open("r", encoding="utf-8") as handle:
            metadata = json.load(handle)

        year = str(metadata.get("year") or "")
        years.append({
            "year": year,
            "status": metadata.get("status", "unknown"),
            "metadataFile": path.name,
        })

        for term in metadata.get("terms") or []:
            course_count = int(term.get("courseCount") or 0)
            total_courses += course_count
            terms.append({
                "year": year,
                "semester": str(term.get("semester") or ""),
                "status": term.get("status", "unknown"),
                "courseCount": course_count,
                "file": term.get("file", ""),
            })

    expected_years = {f"{year:03d}" for year in range(89, 115)}
    archived_years = {item["year"] for item in years}
    missing_years = sorted(expected_years - archived_years)
    partial_years = sorted(
        item["year"] for item in years if item["status"] != "ok"
    )

    status = "ok" if not missing_years and not partial_years else "partial"
    payload = {
        "status": status,
        "range": {"startYear": "089", "endYear": "114"},
        "updatedAtUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "yearCount": len(years),
        "termCount": len(terms),
        "courseCount": total_courses,
        "missingYears": missing_years,
        "partialYears": partial_years,
        "years": years,
        "terms": sorted(terms, key=lambda item: (item["year"], item["semester"])),
    }

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    temp = INDEX_FILE.with_suffix(".json.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp.replace(INDEX_FILE)

    print(
        f"歷史索引完成：{len(years)}個學年度、{len(terms)}個學期、"
        f"{total_courses}門課，狀態{status}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
