"""Tying a chat to its placement: client, start date and consultant name."""

import uuid
from datetime import date

from app.models.enums import TeamsChatMatch
from app.services.teams.chat_match import PlacementCandidate, match_chat
from app.services.teams.chat_titles import ChatTitle

START = date(2026, 9, 21)
ALEX = uuid.uuid4()
ALEXA = uuid.uuid4()
SAM = uuid.uuid4()


def _title(consultant: str = "Alex Sample", client: str = "Demo Client") -> ChatTitle:
    return ChatTitle("DS", consultant, client, START, date(2027, 3, 21))


def _placement(
    consultant_id: uuid.UUID,
    name: str,
    client: str = "Demo Client",
    start: date = START,
) -> PlacementCandidate:
    return PlacementCandidate(uuid.uuid4(), consultant_id, name, client, start)


def test_one_placement_with_the_client_start_and_name_is_a_match() -> None:
    mine = _placement(ALEX, "Alex Sample")
    others = [
        _placement(SAM, "Sam Other"),
        _placement(ALEX, "Alex Sample", start=date(2025, 1, 6)),
        _placement(ALEX, "Alex Sample", client="Other Client"),
    ]

    found = match_chat(_title(), [*others, mine])

    assert found.status == TeamsChatMatch.MATCHED
    assert found.placement_id == mine.placement_id


def test_the_client_matches_ignoring_case_and_spacing() -> None:
    mine = _placement(ALEX, "Alex Sample", client="Demo  client")

    found = match_chat(_title(client="DEMO CLIENT"), [mine])

    assert found.placement_id == mine.placement_id


def test_a_first_name_only_title_matches() -> None:
    mine = _placement(ALEX, "Alex Sample")

    assert match_chat(_title(consultant="Alex"), [mine]).placement_id == (
        mine.placement_id
    )


def test_the_consultant_with_both_names_wins_among_several() -> None:
    mine = _placement(ALEX, "Alex Sample")
    other = _placement(ALEXA, "Alex Other")

    found = match_chat(_title(), [mine, other])

    assert found.status == TeamsChatMatch.MATCHED
    assert found.placement_id == mine.placement_id


def test_two_consultants_the_name_may_mean_need_a_choice() -> None:
    first = _placement(ALEX, "Alex Sample")
    second = _placement(ALEXA, "Alex Other")

    found = match_chat(_title(consultant="Alex"), [first, second])

    assert found.status == TeamsChatMatch.NEEDS_CHOICE
    assert set(found.candidate_ids) == {first.placement_id, second.placement_id}


def test_one_consultant_with_two_such_placements_needs_a_choice() -> None:
    first = _placement(ALEX, "Alex Sample")
    second = _placement(ALEX, "Alex Sample")

    found = match_chat(_title(), [first, second])

    assert found.status == TeamsChatMatch.NEEDS_CHOICE
    assert set(found.candidate_ids) == {first.placement_id, second.placement_id}


def test_no_placement_with_the_name_is_unmatched() -> None:
    found = match_chat(_title(), [_placement(SAM, "Sam Other")])

    assert found.status == TeamsChatMatch.UNMATCHED
    assert found.placement_id is None
    assert found.candidate_ids == []


def test_an_empty_register_is_unmatched() -> None:
    assert match_chat(_title(), []).status == TeamsChatMatch.UNMATCHED
