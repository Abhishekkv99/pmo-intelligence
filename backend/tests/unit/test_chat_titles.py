"""The PMO chat title parser on every title shape seen in the 2026-10-14 survey.

Real titles name real consultants, so each shape is reproduced with made-up
names.
"""

from datetime import date

import pytest

from app.services.teams.chat_titles import (
    ChatTitle,
    TitleFormatError,
    is_pmo_title,
    parse_chat_title,
)

SAMPLE = ChatTitle(
    "DS", "Alex Sample", "Demo Client", date(2026, 9, 21), date(2027, 3, 21)
)


@pytest.mark.parametrize(
    "title",
    [
        # The quick add's strict form
        "PRJ ITC DS - Alex Sample - Demo Client - 21/9/2026 - 21/03/2027",
        # En dashes, as Teams and the folders often have them
        "PRJ ITC DS – Alex Sample – Demo Client – 21/9/2026 – 21/03/2027",
        # No spaces round the dashes
        "PRJ ITC DS-Alex Sample-Demo Client-21/9/2026-21/03/2027",
        "PRJ ITC DS–Alex Sample–Demo Client–21/9/2026–21/03/2027",
        # Spaces on one side only
        "PRJ ITC DS -Alex Sample- Demo Client - 21/9/2026 -21/03/2027",
        # The prefix with a dash
        "PRJ ITC-DS - Alex Sample - Demo Client - 21/9/2026 - 21/03/2027",
        "PRJ ITC - DS - Alex Sample - Demo Client - 21/9/2026 - 21/03/2027",
        "prj itc DS - Alex Sample - Demo Client - 21/9/2026 - 21/03/2027",
        # Dates in brackets, each or both
        "PRJ ITC DS - Alex Sample - Demo Client - (21/9/2026) - (21/03/2027)",
        "PRJ ITC DS - Alex Sample - Demo Client (21/9/2026 - 21/03/2027)",
        "PRJ ITC DS - Alex Sample - Demo Client - [21/9/2026 - 21/3/2027]",
        # Other date forms
        "PRJ ITC DS - Alex Sample - Demo Client - 21/9/26 - 21/3/27",
        "PRJ ITC DS - Alex Sample - Demo Client - 21-9-26 - 21-3-27",
        "PRJ ITC DS - Alex Sample - Demo Client - 21-09-2026 - 21-03-2027",
        "PRJ ITC DS - Alex Sample - Demo Client - 2026-09-21 - 2027-03-21",
        "PRJ ITC DS - Alex Sample - Demo Client - 21/9/2026 - 2027-03-21",
        # Extra spaces anywhere
        "  PRJ  ITC DS  -  Alex   Sample -  Demo  Client -  21/9/2026  -  21/3/2027 ",
    ],
)
def test_reads_every_title_shape_seen(title: str) -> None:
    assert parse_chat_title(title) == SAMPLE


def test_a_hyphenated_name_survives_in_a_spaced_title() -> None:
    parsed = parse_chat_title(
        "PRJ ITC BD - Jean-Paul Example - Coca-Demo Ltd - 1/9/2026 - 31/3/2027"
    )

    assert parsed.consultant == "Jean-Paul Example"
    assert parsed.client == "Coca-Demo Ltd"
    assert parsed.stack == "BD"


def test_a_first_name_only_and_a_long_stack_are_kept() -> None:
    parsed = parse_chat_title(
        "PRJ ITC Data Eng - Priya - Demo Bank - 1-10-26 - 31-3-27"
    )

    assert parsed == ChatTitle(
        "Data Eng", "Priya", "Demo Bank", date(2026, 10, 1), date(2027, 3, 31)
    )


@pytest.mark.parametrize(
    ("title", "reason"),
    [
        ("Project Alex Sample - 1/9/2026 - 31/3/2027", "does not start with 'PRJ ITC'"),
        ("PRJ ITCX DS - Alex - Demo - 1/9/2026 - 31/3/2027", "does not start"),
        ("PRJ ITC DS - Alex Sample - Demo Client", "found 0"),
        ("PRJ ITC DS - Alex Sample - Demo Client - 1/9/2026", "found 1"),
        ("PRJ ITC - Alex Sample - Demo Client - 1/9/2026 - 31/3/2027", "found 2 part"),
        (
            "PRJ ITC DS - Alex Sample - Demo Client - Payments - 1/9/2026 - 31/3/2027",
            "found 4 part",
        ),
        ("PRJ ITC DS - Alex - Demo - 1/9/2026 - 31/3/2027 old", "must end the title"),
        (
            "PRJ ITC DS - Alex - Demo - 31/2/2026 - 31/3/2027",
            "'31/2/2026' is not a real",
        ),
        ("PRJ ITC DS - Alex - Demo - 1/9/2027 - 31/3/2027", "end date is before"),
    ],
)
def test_titles_it_cannot_read_give_the_reason(title: str, reason: str) -> None:
    with pytest.raises(TitleFormatError, match=reason):
        parse_chat_title(title)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("PRJ ITC DS - Alex - Demo - 1/9/2026 - 31/3/2027", True),
        ("prj itc-DS whatever", True),
        ("PRJ ITC", True),
        ("Team lunch", False),
        ("PRJ ITCX", False),
        ("", False),
        (None, False),
    ],
)
def test_is_pmo_title(title: str | None, expected: bool) -> None:
    assert is_pmo_title(title) is expected
