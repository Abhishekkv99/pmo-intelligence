"""Reading the register CSV: the checks on the file itself, before any row.

Problems with the file (size, encoding, columns, emptiness) refuse the whole
upload with 422; problems with a row are reported per row by the import
(tests/integration/test_register_import.py).
"""

import pytest

from app.services.register_import import COLUMNS, MAX_ROWS, read_rows
from app.services.register_service import normalize_name, tidy
from app.utils.exceptions import ValidationError

HEADER = ",".join(COLUMNS)
ROW = "Asha Rao,asha@example.com,Barclays,Payments,,,,,2026-08-17,2027-02-17,,"


def _csv(*lines: str, bom: bool = False) -> bytes:
    text = "\r\n".join(lines) + "\r\n"
    return (("﻿" if bom else "") + text).encode("utf-8")


class TestReadRows:
    def test_reads_rows_with_their_line_numbers(self) -> None:
        rows = read_rows(_csv(HEADER, ROW, ROW.replace("Asha Rao", "Ben Ode")))

        assert [r.number for r in rows] == [2, 3]
        assert rows[0].get("consultant_full_name") == "Asha Rao"
        assert rows[1].get("consultant_full_name") == "Ben Ode"

    def test_excel_bom_is_ignored(self) -> None:
        rows = read_rows(_csv(HEADER, ROW, bom=True))

        assert rows[0].get("consultant_full_name") == "Asha Rao"

    def test_header_case_and_spaces_are_ignored(self) -> None:
        header = ",".join(f" {c.upper()} " for c in COLUMNS)

        rows = read_rows(_csv(header, ROW))

        assert rows[0].get("client_name") == "Barclays"

    def test_cells_are_trimmed(self) -> None:
        rows = read_rows(_csv(HEADER, ROW.replace("Barclays", "  Barclays  ")))

        assert rows[0].get("client_name") == "Barclays"

    def test_blank_lines_are_skipped(self) -> None:
        rows = read_rows(_csv(HEADER, ",,,,,,,,,,,", ROW, ""))

        assert len(rows) == 1
        assert rows[0].number == 3

    def test_missing_and_unknown_columns_are_named(self) -> None:
        header = HEADER.replace("rate_band", "rate")

        with pytest.raises(ValidationError) as exc:
            read_rows(_csv(header, ROW))

        assert "missing columns: rate_band" in exc.value.message
        assert "unknown columns: rate" in exc.value.message

    def test_not_utf8_is_refused(self) -> None:
        content = _csv(HEADER, ROW.replace("Asha", "Ásha")).decode().encode("cp1252")

        with pytest.raises(ValidationError, match="CSV UTF-8"):
            read_rows(content)

    def test_over_one_megabyte_is_refused(self) -> None:
        content = _csv(HEADER) + b"x" * (1024 * 1024)

        with pytest.raises(ValidationError, match="larger than 1 MB"):
            read_rows(content)

    @pytest.mark.parametrize("content", [b"", HEADER.encode()])
    def test_empty_file_or_header_only_is_refused(self, content: bytes) -> None:
        with pytest.raises(ValidationError, match="empty|no rows"):
            read_rows(content)

    def test_more_than_the_row_limit_is_refused(self) -> None:
        content = _csv(HEADER, *([ROW] * (MAX_ROWS + 1)))

        with pytest.raises(ValidationError, match=f"more than {MAX_ROWS} rows"):
            read_rows(content)


class TestNames:
    def test_normalize_name_folds_case_and_spacing(self) -> None:
        assert normalize_name("  Capital   One ") == "capital one"
        assert normalize_name("STRASSE") == normalize_name("straße")

    def test_tidy_keeps_case(self) -> None:
        assert tidy("  Capital   One ") == "Capital One"
