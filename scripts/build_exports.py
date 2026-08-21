#!/usr/bin/env python3
"""將快取的完整案件 JSON 標準化為跨年度 CSV。"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


CASE_FIELDS = [
    "case_key", "year", "announcement_date", "award_date", "unit_id", "unit_name", "job_number",
    "title", "procurement_category", "tender_method", "award_method", "budget_amount", "award_amount",
    "winner_count", "winning_vendors", "source_url", "raw_file",
]
VENDOR_FIELDS = [
    "case_key", "year", "unit_name", "job_number", "title", "award_date", "vendor_name", "vendor_id",
    "case_award_amount", "winner_count", "amount_warning",
]
QUALITY_FIELDS = ["year", "date", "stage", "unit_id", "job_number", "issue", "raw_file"]


def first_suffix(detail: dict, suffixes: tuple[str, ...]) -> str:
    for suffix in suffixes:
        for key, value in detail.items():
            if key.endswith(suffix) and value not in (None, ""):
                return str(value).strip()
    return ""


def parse_amount(value: object) -> int | None:
    if value in (None, ""):
        return None
    normalized = re.sub(r"[^0-9.-]", "", str(value))
    try:
        return round(float(normalized))
    except ValueError:
        return None


def roc_to_iso(value: str) -> str:
    value = value.strip()
    match = re.search(r"(\d{2,3})[\/.-](\d{1,2})[\/.-](\d{1,2})", value)
    if not match:
        return value
    return f"{int(match.group(1)) + 1911:04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def detail_for_record(payload: dict, date: object, filename: object) -> dict:
    records = payload.get("records", [])
    for record in records if isinstance(records, list) else []:
        if str(record.get("date")) == str(date) and str(record.get("filename")) == str(filename):
            return record.get("detail", {}) if isinstance(record.get("detail"), dict) else {}
    return {}


def winners(detail: dict, brief: dict) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []

    def add(name: object, vendor_id: object = "") -> None:
        clean_name = str(name).strip()
        clean_id = str(vendor_id).strip()
        if not clean_name:
            return
        for index, (existing_name, existing_id) in enumerate(found):
            if existing_name == clean_name:
                if not existing_id and clean_id:
                    found[index] = (existing_name, clean_id)
                return
        found.append((clean_name, clean_id))

    # 以「決標品項:第N品項:得標廠商N」為主要來源；不能用字串包含判斷，
    # 因為「未得標廠商」也包含「得標廠商」四字。
    for key, value in detail.items():
        is_winner_section = bool(re.search(r"(?:^|:)得標廠商\d*(?::|$)", key))
        is_loser_section = bool(re.search(r"(?:^|:)未得標廠商\d*(?::|$)", key))
        if is_winner_section and not is_loser_section and key.endswith(("廠商名稱", "得標廠商")) and value:
            prefix = key.rsplit(":", 1)[0]
            vendor_id = str(detail.get(prefix + ":廠商代碼", "")).strip()
            add(value, vendor_id)

    # 部分公告只在投標廠商區標示「是否得標＝是」。
    if not found:
        for key, value in detail.items():
            if key.endswith(":是否得標") and str(value).strip() == "是":
                prefix = key.rsplit(":", 1)[0]
                add(detail.get(prefix + ":廠商名稱", ""), detail.get(prefix + ":廠商代碼", ""))

    if not found:
        companies = brief.get("companies", {}) if isinstance(brief, dict) else {}
        names = companies.get("names", []) if isinstance(companies, dict) else []
        ids = companies.get("ids", []) if isinstance(companies, dict) else []
        name_keys = companies.get("name_key", {}) if isinstance(companies, dict) else {}
        for index, name in enumerate(names if isinstance(names, list) else []):
            paths = name_keys.get(name, []) if isinstance(name_keys, dict) else []
            winner_path = any(
                re.search(r"(?:^|:)得標廠商\d*(?::|$)", str(path))
                and not re.search(r"(?:^|:)未得標廠商\d*(?::|$)", str(path))
                for path in paths
            )
            if winner_path:
                add(name, ids[index] if index < len(ids) else "")
    return found


def normalize(index_record: dict, detail: dict, raw_file: str) -> tuple[dict, list[dict], list[dict]]:
    year = int(str(index_record.get("date"))[:4])
    case_key = "|".join(str(index_record.get(key, "")) for key in ("unit_id", "job_number", "date", "filename"))
    brief = index_record.get("brief", {})
    vendor_pairs = winners(detail, brief)
    award_amount = parse_amount(first_suffix(detail, ("總決標金額", "決標金額", "決標價")))
    budget_amount = parse_amount(first_suffix(detail, ("預算金額",)))
    title = first_suffix(detail, ("標案名稱",)) or str(brief.get("title", ""))
    award_date = roc_to_iso(first_suffix(detail, ("決標日期",)))
    source_url = str(detail.get("url", "")) or str(index_record.get("url", ""))
    case = {
        "case_key": case_key, "year": year, "announcement_date": str(index_record.get("date", "")),
        "award_date": award_date, "unit_id": index_record.get("unit_id", ""),
        "unit_name": index_record.get("unit_name", ""), "job_number": index_record.get("job_number", ""),
        "title": title, "procurement_category": first_suffix(detail, ("標的分類",)),
        "tender_method": first_suffix(detail, ("招標方式",)), "award_method": first_suffix(detail, ("決標方式",)),
        "budget_amount": budget_amount, "award_amount": award_amount, "winner_count": len(vendor_pairs),
        "winning_vendors": "；".join(name for name, _ in vendor_pairs), "source_url": source_url,
        "raw_file": raw_file,
    }
    vendor_rows = [{
        "case_key": case_key, "year": year, "unit_name": case["unit_name"], "job_number": case["job_number"],
        "title": title, "award_date": award_date, "vendor_name": name, "vendor_id": vendor_id,
        "case_award_amount": award_amount, "winner_count": len(vendor_pairs),
        "amount_warning": "多家得標時不可按廠商列直接加總案件金額" if len(vendor_pairs) > 1 else "",
    } for name, vendor_id in vendor_pairs]
    issues = []
    for condition, issue in ((not detail, "找不到對應案件詳情"), (award_amount is None, "缺少可解析的決標金額"), (not vendor_pairs, "缺少得標廠商")):
        if condition:
            issues.append({
                "year": year, "date": case["announcement_date"], "stage": "normalize", "unit_id": case["unit_id"],
                "job_number": case["job_number"], "issue": issue, "raw_file": raw_file,
            })
    return case, vendor_rows, issues


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def annual_rows(output: Path, prefix: str) -> list[dict]:
    """讀取 prefix_YYYY.csv；刻意排除 procurement_master.csv 等彙整檔。"""
    pattern = re.compile(rf"^{re.escape(prefix)}_(\\d{{4}})\\.csv$")
    paths = sorted(path for path in output.glob(f"{prefix}_*.csv") if pattern.fullmatch(path.name))
    return [row for path in paths for row in read_csv(path)]


def rebuild_combined(output: Path) -> tuple[int, int, int]:
    """由所有年度檔重建跨年度總表，避免單一年份工作流覆蓋舊資料。"""
    cases = annual_rows(output, "procurement")
    vendors = annual_rows(output, "vendors")
    quality = annual_rows(output, "data_quality")
    cases.sort(key=lambda row: (row["year"], row["announcement_date"], row["unit_id"], row["job_number"]))
    vendors.sort(key=lambda row: (row["year"], row["award_date"], row["case_key"], row["vendor_name"]))
    quality.sort(key=lambda row: (row["year"], row["date"], row["stage"], row["unit_id"], row["job_number"], row["issue"]))
    write_csv(output / "procurement_master.csv", CASE_FIELDS, cases)
    write_csv(output / "vendors.csv", VENDOR_FIELDS, vendors)
    write_csv(output / "data_quality.csv", QUALITY_FIELDS, quality)
    return len(cases), len(vendors), len(quality)


def build(years: list[int], root: Path) -> None:
    output = root / "processed" / "hualien"
    for year in years:
        year_root = root / "raw" / "hualien" / str(year)
        index = json.loads((year_root / "decision_index.json").read_text(encoding="utf-8"))
        cases: list[dict] = []
        year_vendors: list[dict] = []
        year_quality: list[dict] = []
        for record in index:
            raw_path = year_root / "tenders" / (
                f"{record.get('date')}_{record.get('unit_id')}_{str(record.get('job_number')).replace('/', '_')}.json"
            )
            payload = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else {}
            detail = detail_for_record(payload, record.get("date"), record.get("filename"))
            case, vendor_rows, issues = normalize(record, detail, str(raw_path))
            cases.append(case)
            year_vendors.extend(vendor_rows)
            year_quality.extend(issues)
        error_path = year_root / "errors.json"
        if error_path.exists():
            for error in json.loads(error_path.read_text(encoding="utf-8")):
                year_quality.append({**error, "issue": error.get("error", ""), "raw_file": ""})
        cases.sort(key=lambda row: (row["announcement_date"], row["unit_id"], row["job_number"]))
        year_vendors.sort(key=lambda row: (row["award_date"], row["case_key"], row["vendor_name"]))
        year_quality.sort(key=lambda row: (row["date"], row["stage"], row["unit_id"], row["job_number"], row["issue"]))
        write_csv(output / f"procurement_{year}.csv", CASE_FIELDS, cases)
        write_csv(output / f"vendors_{year}.csv", VENDOR_FIELDS, year_vendors)
        write_csv(output / f"data_quality_{year}.csv", QUALITY_FIELDS, year_quality)
    case_count, vendor_count, quality_count = rebuild_combined(output)
    print(f"輸出 {case_count} 案、{vendor_count} 廠商列、{quality_count} 品質問題")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args()
    build(args.years, args.data_root)


if __name__ == "__main__":
    main()
