#!/usr/bin/env python3
"""從 Cloudflare Worker 抓取高大課程，安全更新 GitHub 內的 CSV。"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPARTMENTS_FILE = ROOT / "data" / "departments.json"
CSV_FILE = ROOT / "data" / "nuk_courses_1151.csv"
REMAIN_CSV_FILE = ROOT / "data" / "nuk_course_remain_1151.csv"
METADATA_FILE = ROOT / "data" / "metadata.json"

YEAR = os.getenv("NUK_YEAR", "115")
SEMESTER = os.getenv("NUK_SEMESTER", "1")
PROXY_URL = os.getenv(
    "NUK_PROXY_URL",
    "https://nuk-course-proxy.114961062.workers.dev",
).rstrip("/")
MAX_WORKERS = max(1, min(int(os.getenv("NUK_MAX_WORKERS", "3")), 5))
RETRIES = 3
TIMEOUT_SECONDS = 60

FIELDNAMES = [
    "id", "year", "semester", "college", "department", "departmentName",
    "courseId", "division", "divisionName", "grade", "className",
    "courseName", "credits", "courseType", "capacity", "confirmed",
    "enrolled", "remaining", "teacher", "classroom", "monday", "tuesday",
    "wednesday", "thursday", "friday", "saturday", "sunday",
    "scheduleJson", "restrictions", "notes", "detailUrl", "fetchedAtUtc",
]

REMAIN_FIELDNAMES = [
    "id", "year", "semester", "courseId", "courseName", "department",
    "departmentName", "division", "grade", "className", "capacity",
    "confirmed", "enrolled", "remaining", "isFull",
    "demandExceedsCapacity", "remainUpdatedAt", "status",
]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fetch_department(unit: dict) -> tuple[str, list[dict]]:
    code = unit["code"]
    base_params = {
        "year": YEAR,
        "semester": SEMESTER,
        "department": code,
    }
    last_error: Exception | None = None

    for attempt in range(1, RETRIES + 1):
        try:
            query = urllib.parse.urlencode(
                {**base_params, "refresh": f"{int(time.time())}-{attempt}"}
            )
            url = f"{PROXY_URL}/courses?{query}"
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "NUKCourseData-GitHubActions/1.0",
                },
            )
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.load(response)

            if payload.get("status") != "ok" or not isinstance(payload.get("courses"), list):
                raise ValueError("Worker 回傳格式不正確")

            return code, payload["courses"]
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            last_error = exc
            if attempt < RETRIES:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"{code} 抓取失敗：{last_error}")


def read_existing_rows() -> dict[str, list[dict]]:
    if not CSV_FILE.exists():
        return {}

    grouped: dict[str, list[dict]] = {}
    with CSV_FILE.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            grouped.setdefault(row.get("department", ""), []).append(row)
    return grouped


def flatten_course(course: dict, unit: dict, fetched_at: str) -> dict:
    weekdays = course.get("weekdays") or {}
    return {
        "id": course.get("id", ""),
        "year": course.get("year", YEAR),
        "semester": course.get("semester", SEMESTER),
        "college": unit["college"],
        "department": str(course.get("department") or unit["code"]),
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
        key = row.get("id") or "|".join(
            str(row.get(name, ""))
            for name in ("department", "courseId", "division", "grade", "className")
        )
        unique[key] = row
    return sorted(
        unique.values(),
        key=lambda row: (
            row.get("college", ""), row.get("department", ""),
            row.get("division", ""), row.get("grade", ""),
            row.get("courseId", ""),
        ),
    )


def parse_count(value) -> int | None:
    text = str(value if value is not None else "").strip().replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def build_remain_rows(rows: list[dict]) -> list[dict]:
    remain_rows: list[dict] = []
    for row in rows:
        capacity = parse_count(row.get("capacity"))
        confirmed = parse_count(row.get("confirmed"))
        enrolled = parse_count(row.get("enrolled"))
        remaining = parse_count(row.get("remaining"))
        has_count = any(
            value is not None for value in (capacity, confirmed, enrolled, remaining)
        )

        remain_rows.append({
            "id": row.get("id", ""),
            "year": row.get("year", YEAR),
            "semester": row.get("semester", SEMESTER),
            "courseId": row.get("courseId", ""),
            "courseName": row.get("courseName", ""),
            "department": row.get("department", ""),
            "departmentName": row.get("departmentName", ""),
            "division": row.get("division", ""),
            "grade": row.get("grade", ""),
            "className": row.get("className", ""),
            "capacity": "" if capacity is None else capacity,
            "confirmed": "" if confirmed is None else confirmed,
            "enrolled": "" if enrolled is None else enrolled,
            "remaining": "" if remaining is None else remaining,
            "isFull": "" if remaining is None else str(remaining <= 0).lower(),
            "demandExceedsCapacity": (
                ""
                if capacity is None or enrolled is None
                else str(enrolled > capacity).lower()
            ),
            "remainUpdatedAt": row.get("fetchedAtUtc", ""),
            "status": "ok" if has_count else "unavailable",
        })

    return remain_rows


def write_outputs(rows: list[dict], metadata: dict) -> None:
    CSV_FILE.parent.mkdir(parents=True, exist_ok=True)
    csv_temp = CSV_FILE.with_suffix(".csv.tmp")
    remain_csv_temp = REMAIN_CSV_FILE.with_suffix(".csv.tmp")
    metadata_temp = METADATA_FILE.with_suffix(".json.tmp")

    with csv_temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    with remain_csv_temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=REMAIN_FIELDNAMES, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(build_remain_rows(rows))

    with metadata_temp.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    csv_temp.replace(CSV_FILE)
    remain_csv_temp.replace(REMAIN_CSV_FILE)
    metadata_temp.replace(METADATA_FILE)


def main() -> int:
    departments = load_json(DEPARTMENTS_FILE)
    existing = read_existing_rows()
    unit_by_code = {item["code"].upper(): item for item in departments}
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fetched: dict[str, list[dict]] = {}
    failures: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_department, unit): unit for unit in departments}
        for future in as_completed(futures):
            unit = futures[future]
            try:
                code, courses = future.result()
                fetched[code.upper()] = courses
                print(f"[OK] {code} {unit['name']}：{len(courses)}門", flush=True)
            except Exception as exc:  # 保留完整錯誤供 Actions log 檢查
                failures[unit["code"].upper()] = str(exc)
                print(f"[ERROR] {exc}", file=sys.stderr, flush=True)

    rows: list[dict] = []
    unrecoverable: list[str] = []

    for code, unit in unit_by_code.items():
        if code in fetched:
            rows.extend(flatten_course(course, unit, fetched_at) for course in fetched[code])
            continue

        old_rows = existing.get(code) or existing.get(unit["code"]) or []
        if old_rows:
            rows.extend(old_rows)
            print(f"[FALLBACK] {code} 沿用上一版 {len(old_rows)}門", flush=True)
        else:
            unrecoverable.append(code)

    rows = deduplicate(rows)

    if len(rows) < 100:
        print(f"課程總數異常（僅{len(rows)}門），保留原檔並停止更新。", file=sys.stderr)
        return 1

    # 首次建立時，個別單位可能因來源網站短暫異常而失敗。
    # 只要總課程數已達合理門檻，先建立可用 CSV；後續排程會自動補齊。
    if unrecoverable:
        print(
            "[PARTIAL] 首次建立時下列單位暫未抓取成功，"
            "已先建立 CSV，下次排程將自動補齊："
            + "、".join(unrecoverable),
            file=sys.stderr,
            flush=True,
        )

    metadata = {
        "status": (
            "ok"
            if not failures
            else "partial_initial" if unrecoverable else "partial_with_fallback"
        ),
        "year": YEAR,
        "semester": SEMESTER,
        "updatedAtUtc": fetched_at,
        "courseCount": len(rows),
        "departmentCount": len(departments),
        "failedDepartments": failures,
        "missingDepartments": unrecoverable,
        "source": PROXY_URL,
    }
    write_outputs(rows, metadata)
    print(f"完成：共{len(rows)}門課，寫入 {CSV_FILE.relative_to(ROOT)}")
    print(f"選課人數：寫入 {REMAIN_CSV_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
