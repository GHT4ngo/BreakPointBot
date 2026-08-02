import datetime
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import bot


class FormattingTests(unittest.TestCase):
    def test_fmt_time_clamps_negative_values(self):
        self.assertEqual(bot.fmt_time(-1), "00:00")
        self.assertEqual(bot.fmt_time(125), "02:05")

    def test_progress_bar_clamps_at_one_hundred_percent(self):
        rendered = bot.ANSI_RE.sub("", bot.progress_bar(90, 60))
        self.assertIn("100%", rendered)
        self.assertNotIn("░", rendered)

    def test_swedish_date(self):
        self.assertEqual(
            bot.date_sv(datetime.date(2026, 8, 3)),
            "Måndag 3 augusti",
        )


class EndTimeTests(unittest.TestCase):
    fixed_now = datetime.datetime(
        2026, 8, 3, 13, 15, tzinfo=ZoneInfo("Europe/Stockholm")
    )

    @patch("bot.now_stockholm", return_value=fixed_now)
    def test_parse_colon_time_for_today(self, _mock_now):
        self.assertEqual(
            bot._parse_end_time("14:30"),
            self.fixed_now.replace(hour=14, minute=30, second=0, microsecond=0),
        )

    @patch("bot.now_stockholm", return_value=fixed_now)
    def test_parse_dot_time_for_today(self, _mock_now):
        self.assertEqual(
            bot._parse_end_time("14.30"),
            self.fixed_now.replace(hour=14, minute=30, second=0, microsecond=0),
        )

    def test_rejects_invalid_time(self):
        self.assertIsNone(bot._parse_end_time("25:00"))


class MenuDateTests(unittest.TestCase):
    @patch(
        "bot.today_stockholm",
        return_value=datetime.date(2026, 8, 5),
    )
    def test_target_date_stays_in_current_work_week(self, _mock_today):
        self.assertEqual(
            bot.get_target_date(-2),
            datetime.date(2026, 8, 3),
        )
        self.assertIsNone(bot.get_target_date(3))
        self.assertIsNone(bot.get_target_date(-3))


if __name__ == "__main__":
    unittest.main()
