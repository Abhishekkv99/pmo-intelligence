"""Reading recordings folder names and recording file names.

The names below are synthetic, built in the shapes the 2026-10-08 survey
found (see ``folder_names``); no real consultant's name is used.
"""

from datetime import UTC, date, datetime

import pytest

from app.services.recordings.folder_names import (
    fold,
    parse_folder_name,
    recorded_at_from_filename,
)

LONDON = "Europe/London"


class TestFold:
    def test_accents_case_and_separators_fold_to_plain_words(self) -> None:
        assert fold("Zoë O'Brien – Acme_Bank #-# UK") == "zoe o brien acme bank uk"

    def test_empty_name_folds_to_nothing(self) -> None:
        assert fold("  ") == ""


class TestParseFolderName:
    def test_dated_name_loses_its_routing_suffix(self) -> None:
        parsed = parse_folder_name("14-09-26 - PMO support Priya#-#123456#-#PMO#-#UK")
        assert parsed.display_name == "14-09-26 - PMO support Priya"
        assert parsed.folder_date == date(2026, 9, 14)
        assert parsed.match_text == "pmo support priya"

    def test_pipe_suffix_is_dropped_too(self) -> None:
        parsed = parse_folder_name("02-10-26 - Tomás Reyes#|#ADHOC#|#PMO#|#UK")
        assert parsed.display_name == "02-10-26 - Tomás Reyes"
        assert parsed.match_text == "tomas reyes"

    def test_undated_name_with_en_dashes_and_placement_dates(self) -> None:
        parsed = parse_folder_name(
            "PS PRJ ITC - BD – Priya – Northwind - 1-9-26 - 31-3-27"
        )
        assert parsed.folder_date is None
        assert parsed.display_name.startswith("PS PRJ ITC - BD – Priya")
        assert parsed.match_text == "ps prj itc bd priya northwind 1 9 26 31 3 27"

    def test_impossible_leading_date_is_no_date(self) -> None:
        parsed = parse_folder_name("31-02-26 - Priya")
        assert parsed.folder_date is None
        assert parsed.match_text == "priya"

    def test_empty_name_is_kept_empty(self) -> None:
        parsed = parse_folder_name("")
        assert parsed == parse_folder_name("")
        assert parsed.display_name == ""
        assert parsed.folder_date is None
        assert parsed.match_text == ""


class TestRecordedAtFromFilename:
    def test_talk_recording_in_summer_is_read_as_british_summer_time(self) -> None:
        assert recorded_at_from_filename(
            "Recording 2026-10-01 10-00-00.webm", LONDON
        ) == datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

    def test_talk_recording_in_winter_is_read_as_gmt(self) -> None:
        assert recorded_at_from_filename(
            "Recording 2026-12-01 10-00-00.webm", LONDON
        ) == datetime(2026, 12, 1, 10, 0, tzinfo=UTC)

    def test_versioned_recording_is_read_as_local_time(self) -> None:
        assert recorded_at_from_filename(
            "V1_2026-07-15T143005.mp4", LONDON
        ) == datetime(2026, 7, 15, 13, 30, 5, tzinfo=UTC)

    def test_screen_recording_is_an_instant(self) -> None:
        assert recorded_at_from_filename(
            "screen-recording-1790000000000.webm", LONDON
        ) == datetime.fromtimestamp(1_790_000_000, tz=UTC)

    @pytest.mark.parametrize(
        "name",
        ["Mani 2.webm", "Recording 2026-13-01 10-00-00.webm", "notes.webm", ""],
    )
    def test_name_without_a_valid_time_gives_none(self, name: str) -> None:
        assert recorded_at_from_filename(name, LONDON) is None
