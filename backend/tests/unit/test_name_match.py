"""Tying a folder to a consultant by first or last name (whole words)."""

import uuid

from app.models.enums import FolderMatchStatus
from app.services.recordings.folder_names import fold
from app.services.recordings.name_match import (
    ConsultantName,
    match_folder,
    name_tokens,
)

PRIYA_SHAH = ConsultantName(uuid.uuid4(), "Priya Shah")
PRIYA_PATEL = ConsultantName(uuid.uuid4(), "Priya Anand Patel")
ANN = ConsultantName(uuid.uuid4(), "Ann Brooks")
ZOE = ConsultantName(uuid.uuid4(), "Zoë O'Brien")
MANI = ConsultantName(uuid.uuid4(), "Mani")
RAVI_SHAH = ConsultantName(uuid.uuid4(), "Ravi Shah")


def _match(folder_text: str, *consultants: ConsultantName):  # type: ignore[no-untyped-def]
    return match_folder(fold(folder_text), list(consultants))


class TestNameTokens:
    def test_first_and_last_tokens_only(self) -> None:
        assert name_tokens("Priya Anand Patel") == ("priya", "patel")

    def test_single_name(self) -> None:
        assert name_tokens("Mani") == ("mani",)

    def test_apostrophe_names_keep_their_last_word(self) -> None:
        assert name_tokens("Zoë O'Brien") == ("zoe", "brien")


class TestMatchFolder:
    def test_first_name_alone_matches_one_consultant(self) -> None:
        result = _match("PMO support Ann", ANN, PRIYA_SHAH)
        assert result.status == FolderMatchStatus.MATCHED
        assert result.consultant_id == ANN.id
        assert result.candidate_ids == []

    def test_last_name_alone_matches(self) -> None:
        assert _match("Brooks - Acme", ANN).consultant_id == ANN.id

    def test_part_of_a_word_does_not_match(self) -> None:
        assert _match("PMO support Anna", ANN).status == FolderMatchStatus.UNMATCHED

    def test_accents_and_case_are_ignored(self) -> None:
        assert _match("ZOE - O'BRIEN - Contoso", ZOE).consultant_id == ZOE.id

    def test_middle_name_does_not_match(self) -> None:
        assert _match("Anand onboarding", PRIYA_PATEL).status == (
            FolderMatchStatus.UNMATCHED
        )

    def test_shared_first_name_needs_a_choice(self) -> None:
        result = _match("PMO support Priya", PRIYA_SHAH, PRIYA_PATEL, ANN)
        assert result.status == FolderMatchStatus.NEEDS_CHOICE
        assert result.consultant_id is None
        assert set(result.candidate_ids) == {PRIYA_SHAH.id, PRIYA_PATEL.id}

    def test_the_one_full_name_wins_over_partial_matches(self) -> None:
        result = _match(
            "PRJ ITC - Priya Shah - Northwind", PRIYA_SHAH, PRIYA_PATEL, RAVI_SHAH
        )
        assert result.status == FolderMatchStatus.MATCHED
        assert result.consultant_id == PRIYA_SHAH.id

    def test_two_full_names_offer_only_those_two(self) -> None:
        twin = ConsultantName(uuid.uuid4(), "Priya Shah")
        result = _match("Priya Shah check-in", PRIYA_SHAH, twin, RAVI_SHAH)
        assert result.status == FolderMatchStatus.NEEDS_CHOICE
        assert set(result.candidate_ids) == {PRIYA_SHAH.id, twin.id}

    def test_single_name_consultant_counts_as_a_full_name_match(self) -> None:
        # Mani's one name is all of it; Ravi Shah matches only by surname.
        result = _match("Mani - Shah - review", MANI, RAVI_SHAH)
        assert result.status == FolderMatchStatus.MATCHED
        assert result.consultant_id == MANI.id

    def test_no_name_in_the_folder_is_unmatched(self) -> None:
        assert _match("PRJ ITC BD", ANN, PRIYA_SHAH).status == (
            FolderMatchStatus.UNMATCHED
        )

    def test_empty_folder_name_is_unmatched(self) -> None:
        assert _match("", ANN).status == FolderMatchStatus.UNMATCHED
