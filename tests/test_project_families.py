import tempfile
import unittest
from pathlib import Path

from scripts.analyze_project_families import (
    CASE_FIELDS,
    analyze,
    classify_stage,
    parent_job_number,
    read_csv,
    write_csv,
)


class ProjectFamilyAnalysisTest(unittest.TestCase):
    def test_stage_and_parent_contract(self):
        self.assertEqual(classify_stage("工程-第一次契約變更"), "契約變更／後續擴充")
        self.assertEqual(classify_stage("山海劇場二期興建工程"), "第二期")
        self.assertEqual(parent_job_number("IP1100002562-2", "契約變更／後續擴充"), "IP1100002562")

    def test_shanhai_family_links_changes_and_second_phase(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "procurement_master.csv"
            fields = [
                "case_key", "year", "announcement_date", "award_date", "unit_id", "unit_name",
                "job_number", "title", "budget_amount", "award_amount", "winning_vendors",
                "performance_period", "source_url",
            ]
            rows = [
                {
                    "case_key": "base", "year": 2021, "announcement_date": "20211019",
                    "unit_id": "3.76.55", "unit_name": "花蓮縣政府", "job_number": "IP1100002562",
                    "title": "原住民族山海劇場暨加路蘭廣場興建工程", "budget_amount": 178400565,
                    "award_amount": 173048000, "winning_vendors": "東鼎營造工程有限公司",
                },
                {
                    "case_key": "change1", "year": 2023, "announcement_date": "20231226",
                    "unit_id": "3.76.55", "unit_name": "花蓮縣政府", "job_number": "IP1100002562-1",
                    "title": "原住民族山海劇場暨加路蘭廣場興建工程-第一次契約變更",
                    "budget_amount": 33855077, "award_amount": 32839427,
                    "winning_vendors": "東鼎營造工程有限公司",
                },
                {
                    "case_key": "change2", "year": 2024, "announcement_date": "20240313",
                    "unit_id": "3.76.55", "unit_name": "花蓮縣政府", "job_number": "IP1100002562-2",
                    "title": "原住民族山海劇場暨加路蘭廣場新建工程-第二次契約變更",
                    "budget_amount": 36300499, "award_amount": 34484813,
                    "winning_vendors": "東鼎營造工程有限公司",
                },
                {
                    "case_key": "phase2", "year": 2025, "announcement_date": "20250520",
                    "unit_id": "3.76.55", "unit_name": "花蓮縣政府", "job_number": "AB1140000929",
                    "title": "原住民族山海劇場暨加路蘭廣場二期興建工程",
                    "budget_amount": 113978494, "award_amount": 113978494,
                    "winning_vendors": "東鼎營造工程有限公司",
                },
            ]
            write_csv(source, fields, rows)
            config = root / "families.json"
            config.write_text(
                '{"families":[{"family_id":"shanhai","family_name":"山海劇場",'
                '"include_any":["山海劇場"],"exclude_any":[],"note":"test"}]}',
                encoding="utf-8",
            )
            output = root / "analysis"
            counts = analyze(source, config, output)
            self.assertEqual(counts[:2], (4, 1))
            family = read_csv(output / "project_families.csv")[0]
            self.assertEqual(family["change_announcement_amount"], "67324240")
            self.assertEqual(family["phase_two_award_amount"], "113978494")
            self.assertIn("至少2次契約變更／擴充", family["review_flags"])
            self.assertIn("變更後另有第二期", family["review_flags"])
            self.assertIn("原工程與第二期由同一廠商得標", family["review_flags"])
            cases = {row["case_key"]: row for row in read_csv(output / "project_cases.csv")}
            self.assertEqual(cases["change2"]["parent_job_number"], "IP1100002562")


if __name__ == "__main__":
    unittest.main()
