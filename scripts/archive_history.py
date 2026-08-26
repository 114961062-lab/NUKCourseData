#!/usr/bin/env python3
"""分年度抓取高雄大學歷史課程，輸出與現行115課程相容的CSV。"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPARTMENTS_FILE = Path(
    os.getenv("NUK_DEPARTMENTS_FILE", str(ROOT / "data" / "departments.json"))
).resolve()

PROXY_URL = os.getenv(
    "NUK_PROXY_URL",
    "https://nuk-course-proxy.114961062.workers.dev",
).rstrip("/")

DIVISIONS = ["A", "M", "L", "D", "F", "J", "K", "E", "C"]
SEMESTERS = [item.strip() for item in os.getenv("NUK_SEMESTERS", "1,2,3").split(",") if item.strip()]
RETRIES = max(1, int(os.getenv("NUK_HISTORY_RETRIES", "4")))
TIMEOUT_SECONDS = max(30, int(os.getenv("NUK_HISTORY_TIMEOUT", "180")))
REQUEST_DELAY_SECONDS = max(0.5, float(os.getenv("NUK_HISTORY_DELAY", "1.5")))

FIELDNAMES = [
    "id", "year", "semester", "college", "department", "departmentName",
    "courseId", "division", "divisionName", "grade", "className",
    "courseName", "credits", "courseType", "capacity", "confirmed",
    "enrolled", "remaining", "teacher", "classroom", "monday", "tuesday",
    "wednesday", "thursday", "friday", "saturday", "sunday",
    "scheduleJson", "restrictions", "notes", "detailUrl", "fetchedAtUtc",
]

HISTORICAL_UNIT_OVERRIDES = {
    "FIN": {"college": "管理學院", "name": "財務金融學系（歷史代碼）"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", required=True, help="三位數民國學年度，例如089或114")
    parser.add_argument("--output-dir", default="build/history")
    parser.add_argument("--existing-dir", default="data/history")
    return parser.parse_args()


def validate_year(year: str) -> None:
    if not re.fullmatch(r"\d{3}", year):
        raise ValueError("year 必須是三位數，例如089或114")
    if not 89 <= int(year) <= 114:
        raise ValueError("本歷史封存程式僅處理089至114學年度")


def load_units() -> dict[str, dict]:
    with DEPARTMENTS_FILE.open("r", encoding="utf-8") as handle:
        rows = json.load(handle)

    units = {
        str(row["code"]).upper(): {
            "college": str(row.get("college") or ""),
            "name": str(row.get("name") or row["code"]),
        }
        for row in rows
    }
    units.update(HISTORICAL_UNIT_OVERRIDES)
    return units


def fetch_division(year: str, semester: str, division: str) -> dict:
    params = urllib.parse.urlencode({
        "year": year,
        "semester": semester,
        "division": division,
    })
    url = f"{PROXY_URL}/courses?{params}"
    last_error: Exception | None = None

    for attempt in range(1, RETRIES + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "NUKCourseData-HistoryArchive/1.0",
                },
            )
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.load(response)

            if payload.get("status") != "ok" or not isinstance(payload.get("courses"), list):
                raise ValueError("課程服務回傳格式不正確")

            return payload
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            if attempt < RETRIES:
                wait_seconds = 2 ** attempt
                print(
                    f"[RETRY] {year}-{semester} 部別{division} 第{attempt}次失敗，"
                    f"{wait_seconds}秒後重試：{exc}",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(wait_seconds)

    raise RuntimeError(f"{year}-{semester} 部別{division}抓取失敗：{last_error}")


def read_existing_by_division(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        return {}

    grouped: dict[str, list[dict]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            division = str(row.get("division") or "").upper()
            grouped.setdefault(division, []).append(row)
    return grouped


def flatten_course(course: dict, units: dict[str, dict], fetched_at: str) -> dict:
    weekdays = course.get("weekdays") or {}
    department = str(course.get("department") or "").strip()
    unit = units.get(department.upper(), {
        "college": "歷史開課單位",
        "name": department or "未辨識開課單位",
    })

    return {
        "id": course.get("id", ""),
        "year": course.get("year", ""),
        "semester": course.get("semester", ""),
        "college": unit["college"],
        "department": department,
        "departmentName": unit["name"],
        "courseId": course.get("courseId", ""),
        "division": course.get("division", ""),
        "divisionName": course.get("divisionName", ""),
        "grade": course.get("grade", ""),
        "className": course.get("className", ""),
        "courseName": course.get("courseName", ""),
        "credits": course.get("credits", ""),
        "courseType": course.get("courseType", ""),
        "capacity": course.get("capacity", ""),
        "confirmed": course.get("confirmed", ""),
        "enrolled": course.get("enrolled", ""),
        "remaining": course.get("remaining", ""),
        "teacher": course.get("teacher", ""),
        "classroom": course.get("classroom", ""),
        "monday": weekdays.get("monday", ""),
        "tuesday": weekdays.get("tuesday", ""),
        "wednesday": weekdays.get("wednesday", ""),
        "thursday": weekdays.get("thursday", ""),
        "friday": weekdays.get("friday", ""),
        "saturday": weekdays.get("saturday", ""),
        "sunday": weekdays.get("sunday", ""),
        "scheduleJson": json.dumps(course.get("schedule") or [], ensure_ascii=False),
        "restrictions": course.get("restrictions", ""),
        "notes": course.get("notes", ""),
        "detailUrl": course.get("detailUrl", ""),
        "fetchedAtUtc": fetched_at,
    }


def deduplicate(rows: list[dict]) -> list[dict]:
    unique: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("id") or "") or "|".join(
            str(row.get(name, ""))
            for name in ("year", "semester", "department", "courseId", "division", "grade", "className")
        )
        unique[key] = row

    return sorted(
        unique.values(),
        key=lambda row: (
            str(row.get("college", "")),
            str(row.get("department", "")),
            str(row.get("division", "")),
            str(row.get("grade", "")),
            str(row.get("courseId", "")),
        ),
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp.replace(path)


def archive_year(year: str, output_dir: Path, existing_dir: Path) -> int:
    units = load_units()
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    year_metadata = {
        "year": year,
        "status": "ok",
        "updatedAtUtc": fetched_at,
        "source": PROXY_URL,
        "terms": [],
    }

    regular_course_count = 0

    for semester in SEMESTERS:
        existing_file = existing_dir / f"nuk_courses_{year}{semester}.csv"
        existing = read_existing_by_division(existing_file)
        rows: list[dict] = []
        failures: dict[str, str] = {}
        fallback_divisions: list[str] = []
        capped_divisions: list[str] = []

        for division in DIVISIONS:
            try:
                payload = fetch_division(year, semester, division)
                courses = payload["courses"]
                pages = int((payload.get("pagination") or {}).get("totalPages") or 1)
                if pages >= 30:
                    capped_divisions.append(division)

                if not courses and existing.get(division):
                    rows.extend(existing[division])
                    fallback_divisions.append(division)
                    print(
                        f"[FALLBACK] {year}-{semester} 部別{division}回傳0門，"
                        f"沿用既有{len(existing[division])}門",
                        flush=True,
                    )
                else:
                    rows.extend(flatten_course(course, units, fetched_at) for course in courses)
                    print(
                        f"[OK] {year}-{semester} 部別{division}：{len(courses)}門／{pages}頁",
                        flush=True,
                    )
            except Exception as exc:
                failures[division] = str(exc)
                if existing.get(division):
                    rows.extend(existing[division])
                    fallback_divisions.append(division)
                    print(
                        f"[FALLBACK] {year}-{semester} 部別{division}失敗，"
                        f"沿用既有{len(existing[division])}門",
                        file=sys.stderr,
                        flush=True,
                    )
                else:
                    print(f"[ERROR] {exc}", file=sys.stderr, flush=True)

            time.sleep(REQUEST_DELAY_SECONDS)

        rows = deduplicate(rows)
        if semester in {"1", "2"}:
            regular_course_count += len(rows)

        status = "ok"
        if failures or capped_divisions:
            status = "partial"
            year_metadata["status"] = "partial"
        if semester in {"1", "2"} and len(rows) < 20:
            status = "suspicious"
            year_metadata["status"] = "partial"

        file_name = f"nuk_courses_{year}{semester}.csv"
        if rows or semester in {"1", "2"}:
            write_csv(output_dir / file_name, rows)
        else:
            file_name = ""

        year_metadata["terms"].append({
            "semester": semester,
            "status": status,
            "courseCount": len(rows),
            "file": file_name,
            "failedDivisions": failures,
            "fallbackDivisions": fallback_divisions,
            "paginationCappedDivisions": capped_divisions,
        })

    if regular_course_count == 0:
        year_metadata["status"] = "failed"

    write_json(output_dir / f"nuk_courses_{year}_metadata.json", year_metadata)
    print(
        f"完成{year}學年度：正式學期共{regular_course_count}門，狀態{year_metadata['status']}",
        flush=True,
    )
    return 1 if year_metadata["status"] == "failed" else 0


def main() -> int:
    args = parse_args()
    validate_year(args.year)
    output_dir = ROOT / args.output_dir
    existing_dir = ROOT / args.existing_dir
    return archive_year(args.year, output_dir, existing_dir)


if __name__ == "__main__":
    raise SystemExit(main())
