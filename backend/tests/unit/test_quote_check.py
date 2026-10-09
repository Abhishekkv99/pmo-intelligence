"""Evidence quotes: found only when the transcript says them, and placed."""

from app.services.quote_check import TranscriptIndex, normalise

UTTERANCES = [
    {"speaker": "A", "text": "Morning, how's it going?", "start_ms": 0},
    {
        "speaker": "B",
        "text": "Honestly, I still can’t get into the staging cluster – "
        "it’s been two weeks.",
        "start_ms": 4_200,
    },
    {
        "speaker": "A",
        "text": "OK.  I'll chase   the platform team today.",
        "start_ms": 9_000,
    },
]


def _index() -> TranscriptIndex:
    return TranscriptIndex(UTTERANCES, None)


class TestNormalise:
    def test_case_curly_quotes_dashes_and_spaces_are_made_plain(self) -> None:
        assert normalise("  It’s  “DONE” — ok\n") == 'it\'s "done" - ok'

    def test_compatibility_characters_are_folded(self) -> None:
        assert normalise("ﬁle…") == "file..."


class TestFind:
    def test_exact_quote_is_found_with_its_speaker_and_moment(self) -> None:
        match = _index().find("I still can’t get into the staging cluster")

        assert match is not None
        assert match.utterance_index == 1
        assert match.speaker == "B"
        assert match.offset_ms == 4_200

    def test_plain_apostrophe_and_hyphen_match_curly_ones(self) -> None:
        match = _index().find("I still can't get into the staging cluster - it's")

        assert match is not None
        assert match.speaker == "B"

    def test_case_and_spacing_are_ignored(self) -> None:
        match = _index().find("i'll CHASE the platform team today")

        assert match is not None
        assert match.offset_ms == 9_000

    def test_surrounding_quote_marks_and_punctuation_are_ignored(self) -> None:
        assert _index().find("“I'll chase the platform team today.”") is not None

    def test_a_reworded_quote_is_not_found(self) -> None:
        assert _index().find("I cannot get into the staging cluster") is None

    def test_words_joined_from_apart_are_not_found(self) -> None:
        assert _index().find("Honestly, the staging cluster") is None

    def test_an_empty_quote_is_not_found(self) -> None:
        assert _index().find(' "..." ') is None

    def test_a_quote_across_two_utterances_is_placed_where_it_starts(self) -> None:
        match = _index().find("how's it going? Honestly, I still")

        assert match is not None
        assert match.utterance_index == 0
        assert match.offset_ms == 0

    def test_without_utterances_the_full_text_is_searched_unplaced(self) -> None:
        index = TranscriptIndex([], "We agreed: the laptop arrives Monday.")

        match = index.find("the laptop arrives Monday")

        assert match is not None
        assert match.speaker is None
        assert match.offset_ms is None
        assert index.find("the laptop arrived") is None
