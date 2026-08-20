import unittest

from scripts.build_exports import parse_amount, roc_to_iso, winners


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



if __name__ == "__main__":
    unittest.main()
