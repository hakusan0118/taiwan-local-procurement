#!/usr/bin/env python3
"""驗證單年度處理後資料的關聯與範圍，不把合理缺漏誤判為零。"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate(root: Path, region: str, year: int, unit_prefix: str) -> dict[str, int]:
    output = root / "processed" / region
    cases = read_csv(output / f"procurement_{year}.csv")
    vendors = read_csv(output / f"vendors_{year}.csv")
    quality = read_csv(output / f"data_quality_{year}.csv")
    if not cases:
        raise ValueError(f"{region} {year} 沒有任何決標公告")

    keys = [row["case_key"] for row in cases]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates:
        raise ValueError(f"case_key 重複：{duplicates[0]}")
    wrong_year = [row for row in cases if int(row["year"]) != year]
    if wrong_year:
        raise ValueError(f"混入其他年度案件：{wrong_year[0]['case_key']}")
    wrong_scope = [
        row for row in cases
        if row["unit_id"] != unit_prefix and not row["unit_id"].startswith(unit_prefix + ".")
    ]
    if wrong_scope:
        raise ValueError(f"混入範圍外機關：{wrong_scope[0]['unit_id']}")

    case_keys = set(keys)
    orphan_vendors = [row for row in vendors if row["case_key"] not in case_keys]
    if orphan_vendors:
        raise ValueError(f"廠商列找不到標案：{orphan_vendors[0]['case_key']}")
    vendor_counts = Counter(row["case_key"] for row in vendors)
    mismatch = [
        row for row in cases
        if vendor_counts[row["case_key"]] != int(row.get("winner_count") or 0)
    ]
    if mismatch:
        raise ValueError(f"winner_count 與廠商列數不符：{mismatch[0]['case_key']}")

    missing_amount = sum(not row.get("award_amount") for row in cases)
    missing_vendor = sum(int(row.get("winner_count") or 0) == 0 for row in cases)
    result = {
        "cases": len(cases),
        "vendors": len(vendors),
        "quality": len(quality),
        "missing_amount": missing_amount,
        "missing_vendor": missing_vendor,
    }
    print(
        f"驗證完成：{len(cases)} 案、{len(vendors)} 廠商列、{len(quality)} 品質紀錄；"
        f"金額缺漏 {missing_amount}、廠商缺漏 {missing_vendor}"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--region", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--unit-prefix", required=True)
    args = parser.parse_args()
    validate(args.data_root, args.region, args.year, args.unit_prefix)


if __name__ == "__main__":
    main()
