#!/usr/bin/env python3
"""合併 GitHub Actions 逐月下載的原始資料，供年度匯出使用。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def copy_unique(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != source.read_bytes():
            raise ValueError(f"逐月資料發生不同內容的檔名衝突：{destination}")
        return
    shutil.copy2(source, destination)


def merge_months(input_root: Path, output_root: Path, region: str, year: int) -> dict:
    month_roots = sorted(input_root.glob(f"taichung-{year}-month-*/raw/{region}/{year}"))
    if not month_roots:
        raise FileNotFoundError(f"找不到 {year} 年逐月 artifacts：{input_root}")

    destination = output_root / "raw" / region / str(year)
    decisions: dict[tuple[str, str, str, str], dict] = {}
    errors: list[dict] = []
    covered_dates: set[dt.date] = set()
    prefix = ""

    for month_root in month_roots:
        manifest = read_json(month_root / "manifest.json")
        start = dt.date.fromisoformat(manifest["start_date"])
        end = dt.date.fromisoformat(manifest["end_date"])
        if start.year != year or end.year != year or start > end:
            raise ValueError(f"不合法的月份範圍：{month_root}")
        month_dates = {start + dt.timedelta(days=offset) for offset in range((end - start).days + 1)}
        overlap = covered_dates & month_dates
        if overlap:
            raise ValueError(f"逐月日期重疊：{min(overlap).isoformat()}")
        covered_dates.update(month_dates)
        prefix = prefix or str(manifest.get("scope_unit_prefix", ""))

        for folder in ("daily", "tenders"):
            for source in (month_root / folder).glob("*.json"):
                copy_unique(source, destination / folder / source.name)

        for record in read_json(month_root / "decision_index.json"):
            key = tuple(str(record.get(field, "")) for field in ("date", "unit_id", "job_number", "filename"))
            if key in decisions and decisions[key] != record:
                raise ValueError(f"案件索引內容衝突：{key}")
            decisions[key] = record
        errors.extend(read_json(month_root / "errors.json"))

    expected_start = dt.date(year, 1, 1)
    expected_end = max(covered_dates)
    expected_dates = {
        expected_start + dt.timedelta(days=offset)
        for offset in range((expected_end - expected_start).days + 1)
    }
    missing = sorted(expected_dates - covered_dates)
    if missing:
        raise ValueError(f"逐月資料未連續涵蓋年度：最早缺少 {missing[0].isoformat()}")

    ordered_decisions = sorted(decisions.values(), key=lambda row: tuple(
        str(row.get(field, "")) for field in ("date", "unit_id", "job_number", "filename")
    ))
    unique_errors = {
        tuple(str(row.get(field, "")) for field in ("year", "date", "stage", "unit_id", "job_number", "error")): row
        for row in errors
    }
    ordered_errors = [unique_errors[key] for key in sorted(unique_errors)]
    manifest = {
        "year": year,
        "start_date": expected_start.isoformat(),
        "end_date": expected_end.isoformat(),
        "scope_unit_prefix": prefix,
        "announcement_type": "決標公告",
        "decision_count": len(ordered_decisions),
        "error_count": len(ordered_errors),
        "month_artifact_count": len(month_roots),
        "source_attribution": "CC-BY 歐噴, 工程會",
    }
    write_json(destination / "decision_index.json", ordered_decisions)
    write_json(destination / "errors.json", ordered_errors)
    write_json(destination / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data"))
    parser.add_argument("--region", default="taichung")
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    result = merge_months(args.input_root, args.output_root, args.region, args.year)
    print(
        f"合併 {result['month_artifact_count']} 個月份、"
        f"{result['decision_count']} 筆決標公告、{result['error_count']} 筆品質問題"
    )


if __name__ == "__main__":
    main()
