import json
import tempfile
import unittest
from pathlib import Path

from scripts.merge_monthly_raw import merge_months


class MergeMonthlyRawTest(unittest.TestCase):
    def make_month(self, root: Path, month: str, start: str, end: str, record: dict) -> Path:
        target = root / f"taichung-2015-month-{month}" / "raw" / "taichung" / "2015"
        (target / "daily").mkdir(parents=True)
        (target / "tenders").mkdir()
        (target / "daily" / f"{start.replace('-', '')}.json").write_text("{}", encoding="utf-8")
        (target / "tenders" / f"{month}.json").write_text("{}", encoding="utf-8")
        (target / "decision_index.json").write_text(json.dumps([record]), encoding="utf-8")
        (target / "errors.json").write_text("[]", encoding="utf-8")
        (target / "manifest.json").write_text(json.dumps({
            "start_date": start,
            "end_date": end,
            "scope_unit_prefix": "3.87",
        }), encoding="utf-8")
        return target

    def test_merges_contiguous_months_and_deduplicates_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            common = {"date": "20150101", "unit_id": "3.87.1", "job_number": "A", "filename": "1"}
            self.make_month(base / "artifacts", "01", "2015-01-01", "2015-01-31", common)
            self.make_month(base / "artifacts", "02", "2015-02-01", "2015-02-28", common)

            result = merge_months(base / "artifacts", base / "data", "taichung", 2015)

            self.assertEqual(result["month_artifact_count"], 2)
            self.assertEqual(result["decision_count"], 1)
            self.assertEqual(result["end_date"], "2015-02-28")
            output = base / "data" / "raw" / "taichung" / "2015"
            self.assertTrue((output / "daily" / "20150101.json").exists())
            self.assertTrue((output / "tenders" / "02.json").exists())

    def test_rejects_gap_between_months(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            record = {"date": "20150101", "unit_id": "3.87", "job_number": "A", "filename": "1"}
            self.make_month(base / "artifacts", "01", "2015-01-01", "2015-01-30", record)
            self.make_month(base / "artifacts", "02", "2015-02-01", "2015-02-28", record)
            with self.assertRaisesRegex(ValueError, "2015-01-31"):
                merge_months(base / "artifacts", base / "data", "taichung", 2015)


if __name__ == "__main__":
    unittest.main()
