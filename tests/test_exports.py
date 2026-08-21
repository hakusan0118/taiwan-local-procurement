import tempfile
import unittest
from pathlib import Path

from scripts.build_exports import (
    CASE_FIELDS,
    QUALITY_FIELDS,
    VENDOR_FIELDS,
    parse_amount,
    rebuild_combined,
    roc_to_iso,
    winners,
    write_csv,
)


class ExportHelpersTest(unittest.TestCase):
    def test_parse_amount(self):
        self.assertEqual(parse_amount("新臺幣 1,234,567 元"), 1234567)
        self.assertIsNone(parse_amount(""))

    def test_roc_to_iso(self):
        self.assertEqual(roc_to_iso("112/03/07"), "2023-03-07")

    def test_winners_excludes_unsuccessful_vendors(self):
        detail = {
            "投標廠商:投標廠商1:廠商名稱": "安誼工程顧問有限公司",
            "投標廠商:投標廠商1:是否得標": "是",
            "投標廠商:投標廠商2:廠商名稱": "宇多工程顧問有限公司",
            "投標廠商:投標廠商2:是否得標": "否",
            "決標品項:第1品項:得標廠商1:得標廠商": "安誼工程顧問有限公司",
            "決標品項:第1品項:未得標廠商1:未得標廠商": "宇多工程顧問有限公司",
        }
        self.assertEqual(winners(detail, {}), [("安誼工程顧問有限公司", "")])

    def test_winners_uses_bidder_flag_as_fallback(self):
        detail = {
            "投標廠商:投標廠商1:廠商名稱": "甲公司",
            "投標廠商:投標廠商1:廠商代碼": "12345678",
            "投標廠商:投標廠商1:是否得標": "是",
            "投標廠商:投標廠商2:廠商名稱": "乙公司",
            "投標廠商:投標廠商2:是否得標": "否",
        }
        self.assertEqual(winners(detail, {}), [("甲公司", "12345678")])

    def test_rebuild_combined_keeps_every_annual_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            case_base = {field: "" for field in CASE_FIELDS}
            vendor_base = {field: "" for field in VENDOR_FIELDS}
            quality_base = {field: "" for field in QUALITY_FIELDS}
            write_csv(
                output / "procurement_2010.csv",
                CASE_FIELDS,
                [{**case_base, "case_key": "2010-case", "year": 2010, "announcement_date": "20100102"}],
            )
            write_csv(
                output / "procurement_2023.csv",
                CASE_FIELDS,
                [{**case_base, "case_key": "2023-case", "year": 2023, "announcement_date": "20230102"}],
            )
            # 這個檔名不能被當成年度檔再次讀入。
            write_csv(
                output / "procurement_master.csv",
                CASE_FIELDS,
                [{**case_base, "case_key": "stale", "year": 1999, "announcement_date": "19990101"}],
            )
            write_csv(output / "vendors_2010.csv", VENDOR_FIELDS, [{**vendor_base, "case_key": "2010-case", "year": 2010}])
            write_csv(output / "vendors_2023.csv", VENDOR_FIELDS, [{**vendor_base, "case_key": "2023-case", "year": 2023}])
            write_csv(output / "data_quality_2010.csv", QUALITY_FIELDS, [{**quality_base, "year": 2010, "date": "20100102"}])
            write_csv(output / "data_quality_2023.csv", QUALITY_FIELDS, [{**quality_base, "year": 2023, "date": "20230102"}])

            self.assertEqual(rebuild_combined(output), (2, 2, 2))
            self.assertEqual(
                [row["case_key"] for row in __import__("csv").DictReader(
                    (output / "procurement_master.csv").open(encoding="utf-8-sig")
                )],
                ["2010-case", "2023-case"],
            )


if __name__ == "__main__":
    unittest.main()
