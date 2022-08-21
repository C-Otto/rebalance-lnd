import unittest
from output import (
    format_alias,
    format_ppm,
    format_fee_msat,
    format_fee_msat_red,
    format_fee_msat_white,
    format_fee_sat,
    format_earning,
    format_amount,
    format_amount_green,
    format_error,
    print_bar,
    format_boring_string,
    format_success,
    format_channel_id,
    format_warning,
)


class TestFormat(unittest.TestCase):
    def test_format_alias(self):
        """Verifies format output"""
        test_aliases = [
            ("utf-node", "\x1b[1mutf-node\x1b[22m"),
            ("node", "\x1b[1mnode\x1b[22m"),
            ("my-node", "\x1b[1mmy-node\x1b[22m"),
            (1, "\x1b[1m1\x1b[22m"),
            ("1", "\x1b[1m1\x1b[22m"),
            (b"1", "\x1b[1mb'1'\x1b[22m"),
            (True, "\x1b[1mTrue\x1b[22m"),
            ("True", "\x1b[1mTrue\x1b[22m"),
            (False, "\x1b[1mFalse\x1b[22m"),
            ("False", "\x1b[1mFalse\x1b[22m"),
            (None, "\x1b[1mNone\x1b[22m"),
            ("None", "\x1b[1mNone\x1b[22m"),
        ]

        for test_alias in test_aliases:
            self.assertEqual(format_alias(test_alias[0]), test_alias[1])

    def test_format_ppm(self):
        """Verifies format output"""
        test_cases = [
            (1000, None, "\x1b[1m1,000ppm\x1b[22m"),
            (1000, 1, "\x1b[1m1,000ppm\x1b[22m"),
            (1000, 10, "\x1b[1m     1,000ppm\x1b[22m"),
        ]

        for test_case in test_cases:
            ppm = test_case[0]
            min_length = test_case[1]
            output = test_case[2]

            self.assertEqual(format_ppm(ppm, min_length), output)

    def test_invalid_format_ppm(self):
        """Observes behavior with string input"""

        with self.assertRaises(ValueError) as context:
            ppm = "1000"
            min_length = None
            format_ppm(ppm, min_length)

        self.assertEqual(str(context.exception), "Cannot specify ',' with 's'.")

    def test_fee_msat(self):
        """Verifies format output"""
        test_cases = [
            (1000, None, "\x1b[36m1,000 mSAT\x1b[39m"),
            (1000, 1, "\x1b[36m1,000 mSAT\x1b[39m"),
            (1000, 10, "\x1b[36m     1,000 mSAT\x1b[39m"),
        ]

        for test_case in test_cases:
            ppm = test_case[0]
            min_length = test_case[1]
            output = test_case[2]

            self.assertEqual(format_fee_msat(ppm, min_length), output)

    def test_invalid_format_fee_msat(self):
        """Observes behavior with string input"""

        with self.assertRaises(ValueError) as context:
            ppm = "1000"
            min_length = None
            format_fee_msat(ppm, min_length)

        self.assertEqual(str(context.exception), "Cannot specify ',' with 's'.")

    def test_fee_msat_red(self):
        """Verifies format output"""
        test_cases = [
            (1000, None, "\x1b[31m1,000 mSAT\x1b[39m"),
            (1000, 1, "\x1b[31m1,000 mSAT\x1b[39m"),
            (1000, 10, "\x1b[31m     1,000 mSAT\x1b[39m"),
        ]

        for test_case in test_cases:
            ppm = test_case[0]
            min_length = test_case[1]
            output = test_case[2]

            self.assertEqual(format_fee_msat_red(ppm, min_length), output)

    def test_fee_msat_white(self):
        """Verifies format output"""
        test_cases = [
            (1000, None, "\x1b[97m1,000 mSAT\x1b[39m"),
            (1000, 1, "\x1b[97m1,000 mSAT\x1b[39m"),
            (1000, 10, "\x1b[97m     1,000 mSAT\x1b[39m"),
        ]

        for test_case in test_cases:
            ppm = test_case[0]
            min_length = test_case[1]
            output = test_case[2]

            self.assertEqual(format_fee_msat_white(ppm, min_length), output)

    def test_fee_sat(self):
        """Verifies format output"""
        test_cases = [
            (1000, "\x1b[36m1,000 sats\x1b[39m"),
            (1, "\x1b[36m1 sats\x1b[39m"),
        ]

        for test_case in test_cases:
            fee_sat = test_case[0]
            output = test_case[1]

            self.assertEqual(format_fee_sat(fee_sat), output)

    def test_format_earning(self):
        """Verifies format output"""
        test_cases = [
            (1000, None, "\x1b[32m1,000 mSAT\x1b[39m"),
            (1000, 1, "\x1b[32m1,000 mSAT\x1b[39m"),
            (1000, 10, "\x1b[32m     1,000 mSAT\x1b[39m"),
        ]

        for test_case in test_cases:
            msat = test_case[0]
            min_width = test_case[1]
            output = test_case[2]

            self.assertEqual(format_earning(msat, min_width), output)

    def test_format_amount(self):
        """Verifies format output"""
        test_cases = [
            (1000, None, "\x1b[33m1,000\x1b[39m"),
            (1000, 1, "\x1b[33m1,000\x1b[39m"),
            (1000, 10, "\x1b[33m     1,000\x1b[39m"),
        ]

        for test_case in test_cases:
            amount = test_case[0]
            min_width = test_case[1]
            output = test_case[2]

            self.assertEqual(format_amount(amount, min_width), output)

    def test_format_amount_green(self):
        """Verifies format output"""
        test_cases = [
            (1000, 1, "\x1b[32m1,000\x1b[39m"),
            (1000, 10, "\x1b[32m     1,000\x1b[39m"),
        ]

        for test_case in test_cases:
            amount = test_case[0]
            min_width = test_case[1]
            output = test_case[2]

            self.assertEqual(format_amount_green(amount, min_width), output)

    def test_invalid_format_amount_green(self):
        """Observes behavior with invalid min_width"""

        with self.assertRaises(ValueError) as context:
            amount = "1000"
            min_width = None
            format_amount_green(amount, min_width)

        self.assertEqual(str(context.exception), "Invalid format specifier")

    def test_format_boring_string(self):
        """Verifies format output"""
        test_cases = [
            ("hello", "\x1b[40m\x1b[90mhello\x1b[39m\x1b[49m"),
            ("world", "\x1b[40m\x1b[90mworld\x1b[39m\x1b[49m"),
            (True, "\x1b[40m\x1b[90mTrue\x1b[39m\x1b[49m"),
            (None, "\x1b[40m\x1b[90mNone\x1b[39m\x1b[49m"),
        ]

        for test_case in test_cases:
            string = test_case[0]
            output = test_case[1]

            self.assertEqual(format_boring_string(string), output)

    def test_format_channel_id(self):
        """Verifies format output"""
        test_cases = [
            ("hello", "\x1b[40m\x1b[90mhello\x1b[39m\x1b[49m"),
            ("world", "\x1b[40m\x1b[90mworld\x1b[39m\x1b[49m"),
            (True, "\x1b[40m\x1b[90mTrue\x1b[39m\x1b[49m"),
            (None, "\x1b[40m\x1b[90mNone\x1b[39m\x1b[49m"),
        ]

        for test_case in test_cases:
            string = test_case[0]
            output = test_case[1]

            self.assertEqual(format_channel_id(string), output)

    def test_format_success(self):
        """Verifies format output"""
        test_cases = [
            ("hello", "\x1b[46m\x1b[97mhello\x1b[39m\x1b[49m"),
            ("world", "\x1b[46m\x1b[97mworld\x1b[39m\x1b[49m"),
            (True, "\x1b[46m\x1b[97mTrue\x1b[39m\x1b[49m"),
            (None, "\x1b[46m\x1b[97mNone\x1b[39m\x1b[49m"),
        ]

        for test_case in test_cases:
            string = test_case[0]
            output = test_case[1]

            self.assertEqual(format_success(string), output)

    def test_format_warning(self):
        """Verifies format output"""
        test_cases = [
            ("hello", "\x1b[33mhello\x1b[39m"),
            ("world", "\x1b[33mworld\x1b[39m"),
            (True, "\x1b[33mTrue\x1b[39m"),
            (None, "\x1b[33mNone\x1b[39m"),
        ]

        for test_case in test_cases:
            string = test_case[0]
            output = test_case[1]

            self.assertEqual(format_warning(string), output)

    def test_format_error(self):
        """Verifies format output"""
        test_cases = [
            ("hello", "\x1b[31mhello\x1b[39m"),
            ("world", "\x1b[31mworld\x1b[39m"),
            (True, "\x1b[31mTrue\x1b[39m"),
            (None, "\x1b[31mNone\x1b[39m"),
        ]

        for test_case in test_cases:
            string = test_case[0]
            output = test_case[1]

            self.assertEqual(format_error(string), output)

    def test_print_bar(self):
        """Verifies format output"""
        test_cases = [
            (1, 2, "\x1b[1m[\x1b[22m\x1b[1m█\x1b[22m\x1b[1m█\x1b[22m\x1b[1m]\x1b[22m"),
            (
                1,
                10,
                "\x1b[1m[\x1b[22m\x1b[1m█\x1b[22m\x1b[1m█\x1b[22m\x1b[1m█\x1b[22m\x1b[1m█\x1b[22m\x1b[1m█\x1b[22m\x1b[1m█\x1b[22m\x1b[1m█\x1b[22m\x1b[1m█\x1b[22m\x1b[1m█\x1b[22m\x1b[1m█\x1b[22m\x1b[1m]\x1b[22m",
            ),
            (10, 1, "\x1b[1m[\x1b[22m\x1b[1m█\x1b[22m░░░░░░░░░\x1b[1m]\x1b[22m"),
        ]

        for test_case in test_cases:
            width = test_case[0]
            length = test_case[1]
            output = test_case[2]
            self.assertEqual(print_bar(width, length), output)
