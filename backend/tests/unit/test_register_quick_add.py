"""Reading a quick-add line: the Teams chat name format, before any write.

A line that does not follow the format is an error on that line, with the
reason; what a well-formed line writes is pinned against the database
(tests/integration/test_register_quick_add.py).
"""

from datetime import date

import pytest

from app.services.register_quick_add import LineFormatError, ParsedLine, parse_line
from app.services.register_service import normalize_name, tidy

LINE = "PRJ ITC DS - Zeeshan Abbas Jaffar - WTW - 21/9/2026 - 21/03/2027"


class TestParseLine:
    def test_reads_the_chat_name_format(self) -> None:
        assert parse_line(LINE) == ParsedLine(
            stack="DS",
            consultant="Zeeshan Abbas Jaffar",
            client="WTW",
            start_date=date(2026, 9, 21),
            end_date=date(2027, 3, 21),
        )

    def test_en_dashes_separate_like_hyphens(self) -> None:
        line = "PRJ ITC DS – Zeeshan Abbas Jaffar – WTW – 21/9/2026 – 21/03/2027"
        assert parse_line(line) == parse_line(LINE)

    def test_folder_style_short_dates_are_read(self) -> None:
        parsed = parse_line("PRJ ITC BD - Asha Rao - Barclays - 1-9-26 - 31-3-27")
        assert parsed.stack == "BD"
        assert parsed.start_date == date(2026, 9, 1)
        assert parsed.end_date == date(2027, 3, 31)

    def test_spacing_and_prefix_case_are_tidied(self) -> None:
        parsed = parse_line(
            "  prj itc  DS  -  Zeeshan   Abbas Jaffar - WTW  - 21/9/2026 - 21/03/2027 "
        )
        assert parsed.stack == "DS"
        assert parsed.consultant == "Zeeshan Abbas Jaffar"
        assert parsed.client == "WTW"

    def test_a_hyphen_inside_a_name_is_kept(self) -> None:
        parsed = parse_line(
            "PRJ ITC DS - Mary-Jane Smith - Rolls-Royce - 1/10/2026 - 1/4/2027"
        )
        assert parsed.consultant == "Mary-Jane Smith"
        assert parsed.client == "Rolls-Royce"

    @pytest.mark.parametrize(
        ("line", "reason"),
        [
            ("PRJ ITC DS - Zeeshan Abbas Jaffar - WTW - 21/9/2026", "expected 5 parts"),
            (
                "PRJ ITC DS - Zeeshan - WTW - Extra - 21/9/2026 - 21/03/2027",
                "expected 5 parts",
            ),
            ("ITC DS - Zeeshan - WTW - 21/9/2026 - 21/03/2027", "should read 'PRJ ITC"),
            (
                "PRJ ITC - Zeeshan - WTW - 21/9/2026 - 21/03/2027",
                "should read 'PRJ ITC",
            ),
            ("PRJ ITC DS - Zeeshan - WTW - 2026-09-21 - 21/03/2027", "not D/M/YYYY"),
            ("PRJ ITC DS - Zeeshan - WTW - 21/9/26 - 21/03/2027", "not D/M/YYYY"),
            ("PRJ ITC DS - Zeeshan - WTW - 31/2/2026 - 21/03/2027", "not a real date"),
            ("PRJ ITC DS - Zeeshan - WTW - 21/9/2026 - 21/03/2026", "before the start"),
            ("PRJ ITC DS - Zeeshan - WTW - 21/9/2026 — 21/03/2027", "expected 5 parts"),
        ],
    )
    def test_a_line_off_the_format_says_why(self, line: str, reason: str) -> None:
        with pytest.raises(LineFormatError, match=reason):
            parse_line(line)

    def test_an_overlong_stack_is_refused(self) -> None:
        with pytest.raises(LineFormatError, match="longer than 50"):
            parse_line(f"PRJ ITC {'X' * 51} - Asha Rao - WTW - 1/9/2026 - 1/3/2027")


class TestNames:
    def test_normalize_name_folds_case_and_spacing(self) -> None:
        assert normalize_name("  Capital   One ") == "capital one"
        assert normalize_name("STRASSE") == normalize_name("straße")

    def test_tidy_keeps_case(self) -> None:
        assert tidy("  Capital   One ") == "Capital One"
