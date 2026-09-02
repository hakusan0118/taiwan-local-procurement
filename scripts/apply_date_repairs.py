#!/usr/bin/env python3
"""將成功的指定日期補抓結果安全合併回已提交的年度 CSV 與索引。"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path

from build_exports import (
    CASE_FIELDS,
    QUALITY_FIELDS,
    VENDOR_FIELDS,
    rebuild_combined,
    write_csv,
)


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_repairs(data_root: Path, repair_root: Path, region: str, dates: list[str]) -> dict[int, int]:
    normalized_dates = sorted(set(dates))
    if not normalized_dates:
        raise ValueError("沒有指定補抓日期")

    repairs: dict[int, list[Path]] = {}
    for date in normalized_dates:
        try:
            parsed_date = dt.date.fromisoformat(date)
        except ValueError as exc:
            raise ValueError(f"日期格式錯誤：{date}（必須為 YYYY-MM-DD）") from exc
        if parsed_date > dt.date.today():
            raise ValueError(f"不能補抓未來日期：{date}")
        year = int(date[:4])
        run_root = repair_root / date
        raw_root = run_root / "raw" / region / str(year)
        errors = read_json(raw_root / "errors.json")
        if errors:
            raise RuntimeError(f"{date} 補抓仍失敗，停止合併：{errors[0].get('error', '')}")
        repairs.setdefault(year, []).append(run_root)

    changed: dict[int, int] = {}
    output = data_root / "processed" / region
    for year, run_roots in sorted(repairs.items()):
        target_dates = {root.name.replace("-", "") for root in run_roots}
        annual_cases_path = output / f"procurement_{year}.csv"
        annual_vendors_path = output / f"vendors_{year}.csv"
        annual_quality_path = output / f"data_quality_{year}.csv"
        old_cases = read_csv(annual_cases_path)
        old_case_keys = {row["case_key"] for row in old_cases if row.get("announcement_date") in target_dates}

        new_cases: list[dict] = []
        new_vendors: list[dict] = []
        new_quality: list[dict] = []
        new_index: list[dict] = []
        for root in run_roots:
            date = root.name
            processed = root / "processed" / region
            new_cases.extend(read_csv(processed / f"procurement_{year}.csv"))
            new_vendors.extend(read_csv(processed / f"vendors_{year}.csv"))
            new_quality.extend(read_csv(processed / f"data_quality_{year}.csv"))
            new_index.extend(read_json(root / "raw" / region / str(year) / "decision_index.json"))

        unexpected_dates = {
            str(row.get("announcement_date", "")) for row in new_cases
        } - target_dates
        if unexpected_dates:
            raise RuntimeError(f"補抓結果混入非指定日期：{sorted(unexpected_dates)[0]}")
        if not new_index:
            raise RuntimeError(f"{year} 年指定日期補抓結果為 0 案，為避免誤刪原資料而停止合併")

        cases = [row for row in old_cases if row.get("announcement_date") not in target_dates] + new_cases
        vendors = [row for row in read_csv(annual_vendors_path) if row.get("case_key") not in old_case_keys] + new_vendors
        quality = [row for row in read_csv(annual_quality_path) if row.get("date") not in target_dates] + new_quality
        cases.sort(key=lambda row: (row["announcement_date"], row["unit_id"], row["job_number"]))
        vendors.sort(key=lambda row: (row["award_date"], row["case_key"], row["vendor_name"]))
        quality.sort(key=lambda row: tuple(str(row.get(field, "")) for field in ("year", "date", "stage", "unit_id", "job_number", "issue")))
        write_csv(annual_cases_path, CASE_FIELDS, cases)
        write_csv(annual_vendors_path, VENDOR_FIELDS, vendors)
        write_csv(annual_quality_path, QUALITY_FIELDS, quality)

        year_root = data_root / "raw" / region / str(year)
        index = [row for row in read_json(year_root / "decision_index.json") if str(row.get("date")) not in target_dates]
        index.extend(new_index)
        index.sort(key=lambda row: tuple(str(row.get(field, "")) for field in ("date", "unit_id", "job_number", "filename")))
        errors = [row for row in read_json(year_root / "errors.json") if str(row.get("date")) not in target_dates]
        manifest = read_json(year_root / "manifest.json")
        manifest["decision_count"] = len(index)
        manifest["error_count"] = len(errors)
        manifest["repaired_dates"] = sorted(set(manifest.get("repaired_dates", [])) | target_dates)
        write_json(year_root / "decision_index.json", index)
        write_json(year_root / "errors.json", errors)
        write_json(year_root / "manifest.json", manifest)
        changed[year] = len(new_cases)

    rebuild_combined(output)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--repair-root", type=Path, required=True)
    parser.add_argument("--region", default="taichung")
    parser.add_argument("--dates-file", type=Path, required=True)
    args = parser.parse_args()
    dates = [line.strip() for line in args.dates_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    result = apply_repairs(args.data_root, args.repair_root, args.region, dates)
    print("補抓合併完成：" + "、".join(f"{year} 年新增/取代 {count} 案" for year, count in result.items()))


if __name__ == "__main__":
    main()
