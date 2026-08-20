import unittest

from scripts.build_exports import parse_amount, roc_to_iso


class ExportHelpersTest(unittest.TestCase):
    def test_parse_amount(self):
        self.assertEqual(parse_amount("新臺幣 1,234,567 元"), 1234567)
        self.assertIsNone(parse_amount(""))

    def test_roc_to_iso(self):
        self.assertEqual(roc_to_iso("112/03/07"), "2023-03-07")


if __name__ == "__main__":
    unittest.main()
