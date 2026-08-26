#!/usr/bin/env python3
"""由既有採購 CSV 建立可追溯的專案家族、生命週期及查證訊號。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


CASE_FIELDS = [
    "family_id", "family_name", "case_key", "year", "announcement_date", "award_date",
    "unit_id", "unit_name", "job_number", "parent_job_number", "title", "project_stage",
    "match_method", "match_confidence", "budget_amount", "award_amount", "winning_vendors",
    "performance_period", "source_url",
]
FAMILY_FIELDS = [
    "family_id", "family_name", "first_year", "last_year", "span_years", "case_count",
    "related_award_amount", "planning_award_amount", "construction_award_amount",
    "change_announcement_amount", "phase_two_award_amount", "contract_change_count",
    "phase_two_count", "winning_vendors", "review_flags", "amount_note", "config_note",
]
CANDIDATE_FIELDS = [
    "candidate_id", "normalized_core", "first_year", "last_year", "span_years", "case_count",
    "related_award_amount", "unit_names", "titles", "reason",
]

YEAR_PATTERN = re.compile(r"(?:民國)?(?:9\d|1[01]\d|12\d|20\d{2})年度?")
PHASE_TWO_PATTERN = re.compile(r"(?:第[二2]期|二期)")
CHANGE_PATTERN = re.compile(r"(?:契約變更|變更設計|後續擴充)")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def number(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return round(float(str(value).replace(",", "")))
    except ValueError:
        return None


def classify_stage(title: str) -> str:
    if CHANGE_PATTERN.search(title):
        return "契約變更／後續擴充"
    if PHASE_TWO_PATTERN.search(title):
        return "第二期"
    if "可行性" in title:
        return "可行性評估"
    if any(word in title for word in ("設計監造", "規劃設計", "委託監造", "設計技術服務")):
        return "規劃設計監造"
    if any(word in title for word in ("營運", "招商", "策展")):
        return "營運／策展"
    if any(word in title for word in ("典禮", "活動", "參訪", "宣傳")):
        return "活動／宣傳"
    if any(word in title for word in ("新建工程", "興建工程", "工程")):
        return "工程"
    if any(word in title for word in ("規劃", "細部計畫")):
        return "規劃"
    return "其他"


def parent_job_number(job_number: str, stage: str) -> str:
    if stage != "契約變更／後續擴充":
        return ""
    return re.sub(r"-\d+$", "", job_number)


def normalized_core(title: str) -> str:
    value = YEAR_PATTERN.sub("", title)
    value = re.sub(r"第?[一二三四五六七八九十0-9]+次", "", value)
    value = re.sub(
        r"(?:契約變更|變更設計|後續擴充|第[一二三四五六七八九十0-9]+期|"
        r"可行性評估|初步規劃|委託專業服務案?|委託技術服務(?:工作|採購|案)?|"
        r"規劃設計監造|規劃設計|委託監造技術服務工作|勞務採購案?|工程採購案?|"
        r"興建工程|新建工程|工程|計畫|案)",
        "",
        value,
    )
    value = re.sub(r"[\s（）()「」『』暨與及、，,－—_\-/]", "", value)
    return value.strip()


def load_families(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    families = payload.get("families", [])
    if not isinstance(families, list):
        raise ValueError("project family config 的 families 必須是陣列")
    return families


def match_family(title: str, families: list[dict]) -> tuple[dict | None, str]:
    matches = []
    for family in families:
        includes = [alias for alias in family.get("include_any", []) if alias and alias in title]
        excludes = [alias for alias in family.get("exclude_any", []) if alias and alias in title]
        if includes and not excludes:
            matches.append((max(includes, key=len), family))
    if not matches:
        return None, ""
    alias, family = max(matches, key=lambda item: len(item[0]))
    return family, alias


def family_flags(rows: list[dict]) -> list[str]:
    flags = []
    stages = [row["project_stage"] for row in rows]
    years = [int(row["year"]) for row in rows]
    if max(years) - min(years) + 1 >= 8:
        flags.append("跨越8年以上")
    if stages.count("可行性評估") >= 2:
        flags.append("重複可行性評估")
    if stages.count("契約變更／後續擴充") >= 2:
        flags.append("至少2次契約變更／擴充")
    if "契約變更／後續擴充" in stages and "第二期" in stages:
        flags.append("變更後另有第二期")

    original_vendors = {
        row["winning_vendors"] for row in rows
        if row["project_stage"] == "工程" and row["winning_vendors"]
    }
    phase_vendors = {
        row["winning_vendors"] for row in rows
        if row["project_stage"] == "第二期" and row["winning_vendors"]
    }
    if original_vendors & phase_vendors:
        flags.append("原工程與第二期由同一廠商得標")
    return flags


def build_candidates(cases: list[dict], assigned: set[str]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for case in cases:
        if case.get("case_key", "") in assigned:
            continue
        core = normalized_core(case.get("title", ""))
        if len(core) >= 4:
            groups[(case.get("unit_name", ""), core)].append(case)

    candidates = []
    for (unit_name, core), rows in groups.items():
        years = sorted({int(row["year"]) for row in rows})
        if len(rows) < 2 or len(years) < 2:
            continue
        digest = hashlib.sha256(f"{unit_name}|{core}".encode()).hexdigest()[:12]
        candidates.append({
            "candidate_id": f"candidate_{digest}",
            "normalized_core": core,
            "first_year": min(years),
            "last_year": max(years),
            "span_years": max(years) - min(years) + 1,
            "case_count": len(rows),
            "related_award_amount": sum(number(row.get("award_amount")) or 0 for row in rows),
            "unit_names": unit_name,
            "titles": "；".join(dict.fromkeys(row.get("title", "") for row in rows)),
            "reason": "同機關且標題核心相同，尚待人工確認是否為同一專案",
        })
    return sorted(candidates, key=lambda row: (-row["related_award_amount"], -row["span_years"]))


def analyze(source: Path, config: Path, output: Path) -> tuple[int, int, int]:
    cases = read_csv(source)
    families = load_families(config)
    project_cases: list[dict] = []
    assigned: set[str] = set()
    config_by_id = {family["family_id"]: family for family in families}

    for case in cases:
        family, alias = match_family(case.get("title", ""), families)
        if not family:
            continue
        stage = classify_stage(case.get("title", ""))
        project_cases.append({
            "family_id": family["family_id"],
            "family_name": family["family_name"],
            "case_key": case.get("case_key", ""),
            "year": case.get("year", ""),
            "announcement_date": case.get("announcement_date", ""),
            "award_date": case.get("award_date", ""),
            "unit_id": case.get("unit_id", ""),
            "unit_name": case.get("unit_name", ""),
            "job_number": case.get("job_number", ""),
            "parent_job_number": parent_job_number(case.get("job_number", ""), stage),
            "title": case.get("title", ""),
            "project_stage": stage,
            "match_method": f"人工別名：{alias}",
            "match_confidence": "高",
            "budget_amount": number(case.get("budget_amount")),
            "award_amount": number(case.get("award_amount")),
            "winning_vendors": case.get("winning_vendors", ""),
            "performance_period": case.get("performance_period", ""),
            "source_url": case.get("source_url", ""),
        })
        assigned.add(case.get("case_key", ""))

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in project_cases:
        grouped[row["family_id"]].append(row)

    summaries = []
    for family_id, rows in grouped.items():
        years = [int(row["year"]) for row in rows]
        stage_amounts: dict[str, int] = defaultdict(int)
        for row in rows:
            stage_amounts[row["project_stage"]] += row["award_amount"] or 0
        summaries.append({
            "family_id": family_id,
            "family_name": rows[0]["family_name"],
            "first_year": min(years),
            "last_year": max(years),
            "span_years": max(years) - min(years) + 1,
            "case_count": len(rows),
            "related_award_amount": sum(row["award_amount"] or 0 for row in rows),
            "planning_award_amount": sum(stage_amounts[s] for s in ("可行性評估", "規劃", "規劃設計監造")),
            "construction_award_amount": stage_amounts["工程"],
            "change_announcement_amount": stage_amounts["契約變更／後續擴充"],
            "phase_two_award_amount": stage_amounts["第二期"],
            "contract_change_count": sum(row["project_stage"] == "契約變更／後續擴充" for row in rows),
            "phase_two_count": sum(row["project_stage"] == "第二期" for row in rows),
            "winning_vendors": "；".join(dict.fromkeys(
                row["winning_vendors"] for row in rows if row["winning_vendors"]
            )),
            "review_flags": "；".join(family_flags(rows)),
            "amount_note": "相關決標公告金額軌跡；契約變更未確認為新增額前，不可直接稱為最終總造價",
            "config_note": config_by_id[family_id].get("note", ""),
        })

    project_cases.sort(key=lambda row: (row["family_id"], int(row["year"]), row["announcement_date"]))
    summaries.sort(key=lambda row: row["related_award_amount"], reverse=True)
    candidates = build_candidates(cases, assigned)
    write_csv(output / "project_cases.csv", CASE_FIELDS, project_cases)
    write_csv(output / "project_families.csv", FAMILY_FIELDS, summaries)
    write_csv(output / "project_candidates.csv", CANDIDATE_FIELDS, candidates)
    return len(project_cases), len(summaries), len(candidates)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", choices=("hualien", "taichung"), default="hualien")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    source = args.data_root / "processed" / args.region / "procurement_master.csv"
    config = args.config or Path("config") / f"project_families_{args.region}.json"
    output = args.data_root / "analysis" / args.region
    counts = analyze(source, config, output)
    print(f"專案案件 {counts[0]} 筆、已確認家族 {counts[1]} 組、候選家族 {counts[2]} 組")


if __name__ == "__main__":
    main()
