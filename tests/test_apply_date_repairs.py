import csv
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from apply_date_repairs import apply_repairs
from build_exports import CASE_FIELDS, QUALITY_FIELDS, VENDOR_FIELDS, write_csv


class ApplyDateRepairsTest(unittest.TestCase):
    def test_success_replaces_error_and_rebuilds_combined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            out = data / "processed" / "taichung"
            raw = data / "raw" / "taichung" / "2024"
            raw.mkdir(parents=True)
            old_case = {field: "" for field in CASE_FIELDS} | {"case_key": "old", "year": "2024", "announcement_date": "20241220", "unit_id": "3.87", "job_number": "old"}
            write_csv(out / "procurement_2024.csv", CASE_FIELDS, [old_case])
            write_csv(out / "vendors_2024.csv", VENDOR_FIELDS, [])
            write_csv(out / "data_quality_2024.csv", QUALITY_FIELDS, [{"year": "2024", "date": "20241223", "stage": "daily", "issue": "非 JSON"}])
            json.dump([], (raw / "decision_index.json").open("w", encoding="utf-8"))
            json.dump([{"date": "20241223", "error": "非 JSON"}], (raw / "errors.json").open("w", encoding="utf-8"))
            json.dump({"decision_count": 0, "error_count": 1}, (raw / "manifest.json").open("w", encoding="utf-8"))

            repair = root / "repairs" / "2024-12-23"
            repair_raw = repair / "raw" / "taichung" / "2024"
            repair_out = repair / "processed" / "taichung"
            repair_raw.mkdir(parents=True)
            new_case = {field: "" for field in CASE_FIELDS} | {"case_key": "new", "year": "2024", "announcement_date": "20241223", "unit_id": "3.87", "job_number": "new"}
            write_csv(repair_out / "procurement_2024.csv", CASE_FIELDS, [new_case])
            write_csv(repair_out / "vendors_2024.csv", VENDOR_FIELDS, [])
            write_csv(repair_out / "data_quality_2024.csv", QUALITY_FIELDS, [])
            json.dump([], (repair_raw / "errors.json").open("w", encoding="utf-8"))
            json.dump([{"date": "20241223", "unit_id": "3.87", "job_number": "new", "filename": "x"}], (repair_raw / "decision_index.json").open("w", encoding="utf-8"))

            result = apply_repairs(data, root / "repairs", "taichung", ["2024-12-23"])
            self.assertEqual(result, {2024: 1})
            self.assertEqual(len(list(csv.DictReader((out / "procurement_master.csv").open(encoding="utf-8-sig")))), 2)
            self.assertEqual(json.load((raw / "errors.json").open(encoding="utf-8")), [])

    def test_failed_repair_does_not_touch_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repair_raw = root / "repairs" / "2025-01-15" / "raw" / "taichung" / "2025"
            repair_raw.mkdir(parents=True)
            json.dump([{"date": "20250115", "error": "still HTML"}], (repair_raw / "errors.json").open("w", encoding="utf-8"))
            with self.assertRaises(RuntimeError):
                apply_repairs(root / "data", root / "repairs", "taichung", ["2025-01-15"])

    def test_invalid_date_is_rejected_before_reading_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "日期格式錯誤"):
                apply_repairs(root / "data", root / "repairs", "taichung", ["2025-02-30"])


if __name__ == "__main__":
    unittest.main()
