"""Тесты парсера БЖУ."""

import unittest

from app.parser import Macros, ParseError, parse_macros


class ParserTest(unittest.TestCase):
    def test_labeled_ru(self):
        m = parse_macros("Б150 Ж80 У200 К2100")
        self.assertEqual(m, Macros(150.0, 80.0, 200.0, 2100.0))

    def test_plain_four_numbers(self):
        m = parse_macros("150 80 200 2100")
        self.assertEqual(m, Macros(150.0, 80.0, 200.0, 2100.0))

    def test_slashes(self):
        m = parse_macros("150/80/200/2100")
        self.assertEqual(m, Macros(150.0, 80.0, 200.0, 2100.0))

    def test_decimal_comma_and_dot(self):
        m = parse_macros("Б150,5 Ж80.2 У200 К2100")
        self.assertEqual(m, Macros(150.5, 80.2, 200.0, 2100.0))

    def test_english_labels(self):
        m = parse_macros("P150 F80 C200 Cal2100")
        self.assertEqual(m, Macros(150.0, 80.0, 200.0, 2100.0))

    def test_extra_words_ignored(self):
        m = parse_macros("Сегодня Б150 Ж80 У200 К2100")
        self.assertEqual(m, Macros(150.0, 80.0, 200.0, 2100.0))

    def test_out_of_range(self):
        with self.assertRaises(ParseError):
            parse_macros("Б9999 Ж80 У200 К2100")

    def test_three_numbers_rejected(self):
        with self.assertRaises(ParseError):
            parse_macros("150 80 200")

    def test_garbage_rejected(self):
        with self.assertRaises(ParseError):
            parse_macros("привет, как дела")

    def test_empty_rejected(self):
        with self.assertRaises(ParseError):
            parse_macros("   ")


if __name__ == "__main__":
    unittest.main()
