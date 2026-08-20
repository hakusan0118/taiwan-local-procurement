#!/usr/bin/env python3
"""低頻率下載並快取花蓮縣地方政府決標公告。僅使用 Python 標準函式庫。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://pcc-api.openfun.app/api"
USER_AGENT = "taiwan-local-procurement/0.1 (+https://github.com/hakusan0118/taiwan-local-procurement)"


def request_json(url: str, params: dict[str, str] | None, attempts: int, delay: float) -> dict:
    target = url + ("?" + urlencode(params) if params else "")
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(target, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(request, timeout=45) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read().decode("utf-8", errors="replace")
            if "json" not in content_type.lower() and not body.lstrip().startswith(("{", "[")):
                raise ValueError(f"非 JSON 回應：{content_type or 'unknown'}")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("API 頂層不是 JSON object")
            return payload
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(delay * (2**attempt) + random.uniform(0, 0.5))
    assert last_error is not None
    raise last_error


def is_in_scope(unit_id: str, prefix: str) -> bool:
    return unit_id == prefix or unit_id.startswith(prefix + ".")


def iter_dates(year: int, start_date: dt.date | None = None, end_date: dt.date | None = None):
    current = start_date or dt.date(year, 1, 1)
    end = end_date or dt.date(year, 12, 31)
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def safe_name(record: dict) -> str:
    date = str(record.get("date", "unknown"))
    unit = str(record.get("unit_id", "unknown")).replace("/", "_")
    job = str(record.get("job_number", "unknown")).replace("/", "_")
    return f"{date}_{unit}_{job}.json"


def collect(
    year: int,
    root: Path,
    prefix: str,
    delay: float,
    attempts: int,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
) -> None:
    range_start = start_date or dt.date(year, 1, 1)
    range_end = end_date or dt.date(year, 12, 31)
    if range_start.year != year or range_end.year != year:
        raise ValueError("開始與結束日期必須位於指定年度")
    if range_start > range_end:
        raise ValueError("開始日期不得晚於結束日期")
    year_root = root / "raw" / "hualien" / str(year)
    daily_dir = year_root / "daily"
    tender_dir = year_root / "tenders"
    errors: list[dict[str, str]] = []
    decisions: list[dict] = []

    for index, day in enumerate(iter_dates(year, range_start, range_end), 1):
        stamp = day.strftime("%Y%m%d")
        path = daily_dir / f"{stamp}.json"
        try:
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
            else:
                original = request_json(f"{API_BASE}/listbydate", {"date": stamp}, attempts, delay)
                original_records = original.get("records", [])
                if not isinstance(original_records, list):
                    raise ValueError("records 不是陣列")
                payload = {
                    "source_url": f"{API_BASE}/listbydate?date={stamp}",
                    "scope_unit_prefix": prefix,
                    "records": [
                        record for record in original_records
                        if is_in_scope(str(record.get("unit_id", "")), prefix)
                    ],
                }
                write_json(path, payload)
                time.sleep(delay)
            records = payload.get("records", [])
            if not isinstance(records, list):
                raise ValueError("records 不是陣列")
            matched = [
                record for record in records
                if is_in_scope(str(record.get("unit_id", "")), prefix)
                and record.get("brief", {}).get("type") == "決標公告"
            ]
            decisions.extend(matched)
            if matched or index % 30 == 0:
                print(f"{year} {index}: {stamp} 決標 {len(matched)} 筆", flush=True)
        except Exception as exc:  # 保留錯誤後繼續，避免整年結果被單日中斷
            errors.append({"year": str(year), "date": stamp, "stage": "daily", "error": str(exc)})
            print(f"::warning::{stamp} 下載失敗：{exc}", flush=True)

    unique: dict[tuple, dict] = {}
    for record in decisions:
        key = (record.get("date"), record.get("unit_id"), record.get("job_number"), record.get("filename"))
        unique[key] = record
    decisions = sorted(unique.values(), key=lambda row: tuple(str(v) for v in (
        row.get("date", ""), row.get("unit_id", ""), row.get("job_number", ""), row.get("filename", "")
    )))
    write_json(year_root / "decision_index.json", decisions)

    for index, record in enumerate(decisions, 1):
        path = tender_dir / safe_name(record)
        try:
            if not path.exists():
                payload = request_json(
                    f"{API_BASE}/tender",
                    {"unit_id": str(record["unit_id"]), "job_number": str(record["job_number"])},
                    attempts,
                    delay,
                )
                write_json(path, payload)
                time.sleep(delay)
            if index % 50 == 0:
                print(f"{year} 案件詳情 {index}/{len(decisions)}", flush=True)
        except Exception as exc:
            errors.append({
                "year": str(year), "date": str(record.get("date", "")), "stage": "tender",
                "unit_id": str(record.get("unit_id", "")), "job_number": str(record.get("job_number", "")),
                "error": str(exc),
            })
            print(f"::warning::案件 {record.get('job_number')} 下載失敗：{exc}", flush=True)

    write_json(year_root / "errors.json", errors)
    write_json(year_root / "manifest.json", {
        "year": year,
        "start_date": range_start.isoformat(),
        "end_date": range_end.isoformat(),
        "scope_unit_prefix": prefix,
        "announcement_type": "決標公告",
        "decision_count": len(decisions),
        "error_count": len(errors),
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_attribution": "CC-BY 歐噴, 工程會",
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True, choices=range(2000, 2027))
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--unit-prefix", default="3.76.55")
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--start-date", type=dt.date.fromisoformat)
    parser.add_argument("--end-date", type=dt.date.fromisoformat)
    args = parser.parse_args()
    collect(
        args.year, args.data_root, args.unit_prefix, args.delay, args.attempts,
        args.start_date, args.end_date,
    )


if __name__ == "__main__":
    main()
