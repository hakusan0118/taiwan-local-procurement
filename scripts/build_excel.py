#!/usr/bin/env python3
"""Build private Excel analysis workbooks from public procurement CSV files."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


CASE_NUMBER_FIELDS = {"year", "budget_amount", "award_amount", "winner_count"}
VENDOR_NUMBER_FIELDS = {"year", "case_award_amount", "winner_count"}
MONEY_FIELDS = {
    "budget_amount", "award_amount", "case_award_amount", "total_award_amount",
    "average_award_amount", "total_case_award_amount",
}
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def read_csv(path: Path, number_fields: set[str]) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for field in number_fields:
            value = row.get(field, "")
            if value not in (None, ""):
                try:
                    row[field] = int(float(value))
                except ValueError:
                    pass
    return rows


def add_sheet(workbook: Workbook, title: str, rows: list[dict], table_name: str) -> None:
    sheet = workbook.create_sheet(title)
    if not rows:
        sheet.append(["沒有資料"])
        return
    headers = list(rows[0])
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header, "") for header in headers])
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    table = Table(displayName=table_name, ref=sheet.dimensions)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True, showColumnStripes=False)
    sheet.add_table(table)
    for index, header in enumerate(headers, 1):
        values = [str(sheet.cell(row, index).value or "") for row in range(1, min(sheet.max_row, 300) + 1)]
        sheet.column_dimensions[get_column_letter(index)].width = min(max(max(map(len, values)) + 2, 10), 42)
        if header in MONEY_FIELDS:
            for row in range(2, sheet.max_row + 1):
                sheet.cell(row, index).number_format = '#,##0'


def agency_stats(cases: list[dict]) -> list[dict]:
    grouped: dict[str, dict[str, object]] = defaultdict(lambda: {"count": 0, "amounts": []})
    for row in cases:
        name = str(row.get("unit_name", ""))
        grouped[name]["count"] = int(grouped[name]["count"]) + 1
        amount = row.get("award_amount")
        if isinstance(amount, int):
            grouped[name]["amounts"].append(amount)
    result = [{
        "unit_name": name,
        "case_count": values["count"],
        "total_award_amount": sum(amounts),
        "average_award_amount": round(sum(amounts) / len(amounts)) if amounts else 0,
    } for name, values in grouped.items() for amounts in [values["amounts"]]]
    return sorted(result, key=lambda row: row["total_award_amount"], reverse=True)


def vendor_stats(vendors: list[dict]) -> list[dict]:
    cases_by_vendor: dict[str, dict[str, int | None]] = defaultdict(dict)
    for row in vendors:
        name = str(row.get("vendor_name", ""))
        case_key = str(row.get("case_key", ""))
        amount = row.get("case_award_amount")
        if name and case_key:
            cases_by_vendor[name][case_key] = amount if isinstance(amount, int) else None
    result = [{
        "vendor_name": name,
        "case_count": len(cases),
        "total_case_award_amount": sum(amount for amount in cases.values() if amount is not None),
        "note": "多家共同得標案件的總決標金額不可視為單一廠商實得金額",
    } for name, cases in cases_by_vendor.items()]
    return sorted(result, key=lambda row: row["total_case_award_amount"], reverse=True)


def build(year: int, data_root: Path, output_dir: Path) -> Path:
    source = data_root / "processed" / "hualien"
    cases = [row for row in read_csv(source / f"procurement_{year}.csv", CASE_NUMBER_FIELDS) if row.get("year") == year]
    vendors = [row for row in read_csv(source / "vendors.csv", VENDOR_NUMBER_FIELDS) if row.get("year") == year]
    quality = [row for row in read_csv(source / "data_quality.csv", {"year"}) if row.get("year") == year]
    if not cases:
        raise ValueError(f"找不到 {year} 年案件 CSV")

    workbook = Workbook()
    workbook.remove(workbook.active)
    add_sheet(workbook, "案件主表", cases, f"Cases{year}")
    add_sheet(workbook, "得標廠商明細", vendors, f"Vendors{year}")
    add_sheet(workbook, "機關統計", agency_stats(cases), f"Agencies{year}")
    add_sheet(workbook, "廠商統計", vendor_stats(vendors), f"VendorStats{year}")
    add_sheet(workbook, "資料品質", quality, f"Quality{year}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"花蓮縣_{year}_決標分析.xlsx"
    workbook.save(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("excel-output"))
    args = parser.parse_args()
    for year in args.years:
        print(build(year, args.data_root, args.output_dir))


if __name__ == "__main__":
    main()
