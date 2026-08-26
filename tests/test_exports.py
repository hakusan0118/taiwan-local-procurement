import tempfile
import unittest
from pathlib import Path

from scripts.build_exports import (
    CASE_FIELDS,
    QUALITY_FIELDS,
    VENDOR_FIELDS,
    build,
    enrich_case,
    extract_road_names,
    migrate_annual_cases,
    parse_amount,
    quality_sort_key,
    rebuild_combined,
    read_csv,
    roc_to_iso,
    winners,
    write_csv,
)


class ExportHelpersTest(unittest.TestCase):
    def test_build_keeps_regions_in_separate_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for region in ("hualien", "taichung"):
                year_root = root / "raw" / region / "2015"
                year_root.mkdir(parents=True)
                (year_root / "decision_index.json").write_text("[]", encoding="utf-8")
                build([2015], root, region)

            self.assertTrue((root / "processed" / "hualien" / "procurement_2015.csv").exists())
            self.assertTrue((root / "processed" / "taichung" / "procurement_2015.csv").exists())
            self.assertFalse((root / "processed" / "hualien" / "procurement_2016.csv").exists())

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

    def test_extract_road_names_from_title(self):
        self.assertEqual(
            extract_road_names("花蓮市舊市區中山路、中正路及中華路等道路邊溝清淤工程"),
            ["中山路", "中正路", "中華路"],
        )
        self.assertEqual(
            extract_road_names("博愛街與節約街口路面整修工程"),
            ["博愛街", "節約街"],
        )

    def test_extract_road_names_excludes_generic_road_words(self):
        self.assertEqual(extract_road_names("市區路面申挖修補回復工程"), [])
        self.assertEqual(extract_road_names("道路坑洞修補及巡察作業開口契約"), [])

    def test_extract_road_names_excludes_false_road_names(self):
        false_titles = (
            "監控網路設備採購案",
            "無線網路改善工程",
            "編號鄉道及市區道路重要路段養護工程",
            "街路燈維修工程",
            "教育網路及電路改善案",
        )
        for title in false_titles:
            with self.subTest(title=title):
                self.assertEqual(extract_road_names(title), [])

    def test_enrich_case_preserves_source_and_analysis_labels(self):
        case = {
            "title": "博愛街路面整修工程開口契約",
            "performance_location": "花蓮縣－花蓮",
            "performance_region": "",
        }
        enriched = enrich_case(case)
        self.assertEqual(enriched["road_names"], "博愛街")
        self.assertEqual(enriched["road_name_source"], "標案名稱")
        self.assertEqual(enriched["work_tags"], "路面刨鋪")
        self.assertEqual(enriched["is_road_related"], 1)
        self.assertEqual(enriched["is_open_contract"], 1)

    def test_quality_sort_key_allows_download_errors_without_case_fields(self):
        error = {
            "year": 2011,
            "date": "20110101",
            "stage": "daily",
            "issue": "非 JSON 回應",
        }
        self.assertEqual(
            quality_sort_key(error),
            ("2011", "20110101", "daily", "", "", "非 JSON 回應"),
        )

    def test_migrate_annual_cases_backfills_old_csv_without_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            old_fields = ["case_key", "year", "announcement_date", "unit_id", "job_number", "title"]
            write_csv(
                output / "procurement_2010.csv",
                old_fields,
                [{
                    "case_key": "old-case", "year": 2010, "announcement_date": "20100101",
                    "unit_id": "3.76.55.51", "job_number": "A1", "title": "中央路路面整修工程",
                }],
            )
            migrate_annual_cases(output)
            migrated = read_csv(output / "procurement_2010.csv")[0]
            self.assertEqual(migrated["road_names"], "中央路")
            self.assertEqual(migrated["road_name_source"], "標案名稱")
            self.assertEqual(migrated["work_tags"], "路面刨鋪")

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
                [row["case_key"] for row in read_csv(output / "procurement_master.csv")],
                ["2010-case", "2023-case"],
            )


if __name__ == "__main__":
    unittest.main()
