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
    "winner_count", "winning_vendors", "performance_location", "performance_region", "performance_period",
    "road_names", "road_name_source", "work_tags", "is_road_related", "is_open_contract",
    "source_url", "raw_file",
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


ROAD_PATTERN = re.compile(
    r"[\u3400-\u9fffA-Za-z0-9]+?(?:大道|路|街)(?:[一二三四五六七八九十百0-9]+段)?(?:[0-9]+巷)?(?!燈)"
)
GENERIC_ROAD_NAMES = {
    "道路", "市區道路", "既有道路", "重要道路", "主要道路", "聯絡道路", "連絡道路",
    "產業道路", "農路", "人行道", "步道", "車道", "巷道", "市區路", "花蓮市區路", "等道路", "口路",
    "重要路", "街路",
}
# 先移除不可能是實體道路名稱的固定詞組，避免正則把前面的文字一併吃進來。
FALSE_ROAD_PHRASES = (
    "網路", "重要路段", "街路燈", "街路照明", "鐵路", "線路", "電路", "迴路", "水路",
)
ROAD_REJECT_WORDS = {
    "年度", "全鄉", "鄉內", "鎮內", "道路", "農路", "管線", "工程", "修復", "改善",
    "附近", "地號", "路容", "單位", "挖掘", "步道", "部落", "重劃區",
}
WORK_TAG_RULES = (
    ("申挖修補", ("申挖", "挖掘")),
    ("路面刨鋪", ("刨鋪", "刨除", "鋪面", "舖面", "路面整修", "路面改善")),
    ("道路養護", ("道路養護", "道路改善", "道路維護")),
    ("坑洞修補", ("坑洞",)),
    ("排水清淤", ("排水", "下水道", "側溝", "邊溝", "清淤", "疏濬")),
    ("人行道", ("人行道",)),
    ("管線", ("管線", "自來水", "瓦斯", "電纜")),
    ("橋梁", ("橋梁", "橋面",)),
    ("路燈照明", ("路燈", "照明",)),
)


def extract_road_names(text: object) -> list[str]:
    """從公開文字擷取明確路名；無法辨認的「市區道路」等通稱會排除。"""
    value = str(text or "")
    sanitized = value
    for phrase in FALSE_ROAD_PHRASES:
        sanitized = sanitized.replace(phrase, " ")
    found: list[str] = []
    for match in ROAD_PATTERN.findall(sanitized):
        name = re.sub(r"^(?:(?:花蓮縣)?花蓮市|舊市區|市區)+", "", match)
        name = re.sub(r"^[與及暨至到]", "", name)
        stem = re.sub(r"(?:大道|路|街)(?:[一二三四五六七八九十百0-9]+段)?(?:[0-9]+巷)?$", "", name)
        if (
            name in GENERIC_ROAD_NAMES
            or len(name) < 2
            or len(name) > 12
            or not re.search(r"[\u3400-\u9fff]", stem)
            or any(word in name for word in ROAD_REJECT_WORDS)
        ):
            continue
        if name not in found:
            found.append(name)
    return found


def classify_work(title: object) -> list[str]:
    value = str(title or "")
    return [tag for tag, keywords in WORK_TAG_RULES if any(keyword in value for keyword in keywords)]


def enrich_case(case: dict) -> dict:
    """補上可追溯的道路分析欄位；既有年度 CSV 也可由標案名稱回填。"""
    title_roads = extract_road_names(case.get("title", ""))
    location_text = "；".join(filter(None, (
        str(case.get("performance_location", "")),
        str(case.get("performance_region", "")),
    )))
    location_roads = extract_road_names(location_text)
    road_names = title_roads + [name for name in location_roads if name not in title_roads]
    if title_roads and location_roads:
        road_source = "標案名稱＋履約地點"
    elif title_roads:
        road_source = "標案名稱"
    elif location_roads:
        road_source = "履約地點"
    else:
        road_source = ""
    tags = classify_work(case.get("title", ""))
    return {
        **case,
        "road_names": "；".join(road_names),
        "road_name_source": road_source,
        "work_tags": "；".join(tags),
        "is_road_related": 1 if road_names or tags else 0,
        "is_open_contract": 1 if "開口契約" in str(case.get("title", "")) else 0,
    }


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
        "winning_vendors": "；".join(name for name, _ in vendor_pairs),
        "performance_location": first_suffix(detail, ("履約地點",)),
        "performance_region": first_suffix(detail, ("履約地點（含地區）", "履約地點(含地區)")),
        "performance_period": first_suffix(detail, ("履約期限", "履約起迄日期")),
        "source_url": source_url, "raw_file": raw_file,
    }
    case = enrich_case(case)
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


def annual_paths(output: Path, prefix: str) -> list[Path]:
    """找出 prefix_YYYY.csv；刻意排除 procurement_master.csv 等彙整檔。"""
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d{{4}})\.csv$")
    return sorted(path for path in output.glob(f"{prefix}_*.csv") if pattern.fullmatch(path.name))


def annual_rows(output: Path, prefix: str) -> list[dict]:
    return [row for path in annual_paths(output, prefix) for row in read_csv(path)]


def migrate_annual_cases(output: Path) -> None:
    """以標案名稱回填既有年度的道路欄位，不需重新下載舊年度。"""
    for path in annual_paths(output, "procurement"):
        rows = [enrich_case(row) for row in read_csv(path)]
        write_csv(path, CASE_FIELDS, rows)


def quality_sort_key(row: dict) -> tuple[str, str, str, str, str, str]:
    """錯誤紀錄可能沒有機關或案號；缺欄位時以空字串排序。"""
    return tuple(str(row.get(field, "")) for field in ("year", "date", "stage", "unit_id", "job_number", "issue"))


def rebuild_combined(output: Path) -> tuple[int, int, int]:
    """由所有年度檔重建跨年度總表，避免單一年份工作流覆蓋舊資料。"""
    cases = annual_rows(output, "procurement")
    vendors = annual_rows(output, "vendors")
    quality = annual_rows(output, "data_quality")
    cases.sort(key=lambda row: (row["year"], row["announcement_date"], row["unit_id"], row["job_number"]))
    vendors.sort(key=lambda row: (row["year"], row["award_date"], row["case_key"], row["vendor_name"]))
    quality.sort(key=quality_sort_key)
    write_csv(output / "procurement_master.csv", CASE_FIELDS, cases)
    write_csv(output / "vendors.csv", VENDOR_FIELDS, vendors)
    write_csv(output / "data_quality.csv", QUALITY_FIELDS, quality)
    return len(cases), len(vendors), len(quality)


def build(years: list[int], root: Path, region: str = "hualien") -> None:
    output = root / "processed" / region
    for year in years:
        year_root = root / "raw" / region / str(year)
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
        year_quality.sort(key=quality_sort_key)
        write_csv(output / f"procurement_{year}.csv", CASE_FIELDS, cases)
        write_csv(output / f"vendors_{year}.csv", VENDOR_FIELDS, year_vendors)
        write_csv(output / f"data_quality_{year}.csv", QUALITY_FIELDS, year_quality)
    migrate_annual_cases(output)
    case_count, vendor_count, quality_count = rebuild_combined(output)
    print(f"輸出 {case_count} 案、{vendor_count} 廠商列、{quality_count} 品質問題")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--region", choices=("hualien", "taichung"), default="hualien")
    parser.add_argument(
        "--rebuild-only",
        action="store_true",
        help="只由既有年度 CSV 重算分析欄位與跨年度總表，不下載 API",
    )
    args = parser.parse_args()
    if args.rebuild_only:
        output = args.data_root / "processed" / args.region
        migrate_annual_cases(output)
        case_count, vendor_count, quality_count = rebuild_combined(output)
        print(f"重新整理 {case_count} 案、{vendor_count} 廠商列、{quality_count} 品質問題")
        return
    if not args.years:
        parser.error("一般整理模式必須提供 --years；或使用 --rebuild-only")
    build(args.years, args.data_root, args.region)


if __name__ == "__main__":
    main()
