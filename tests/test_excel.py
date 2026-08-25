import unittest

from scripts.build_excel import parse_years


class ExcelYearInputTest(unittest.TestCase):
    def test_single_year(self):
        self.assertEqual(parse_years(["2023"]), [2023])

    def test_tilde_range(self):
        self.assertEqual(parse_years(["2010~2013"]), [2010, 2011, 2012, 2013])

    def test_full_width_tilde_range(self):
        self.assertEqual(parse_years(["2010～2012"]), [2010, 2011, 2012])

    def test_space_separated_years(self):
        self.assertEqual(parse_years(["2010 2012 2023"]), [2010, 2012, 2023])

    def test_reverse_range_fails(self):
        with self.assertRaises(ValueError):
            parse_years(["2023~2010"])


if __name__ == "__main__":
    unittest.main()
