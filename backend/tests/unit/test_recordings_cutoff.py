"""Only calls from RECORDINGS_EARLIEST_DATE on are cataloged (user decision
2026-10-09): a folder is kept when it holds one, with only those calls."""

from datetime import UTC, date, datetime

from app.services.recordings.scanner import SourceObject, keep_recent

EARLIEST = date(2026, 7, 24)
LONDON = "Europe/London"
MODIFIED = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _obj(folder: str, name: str, modified: datetime = MODIFIED) -> SourceObject:
    return SourceObject(
        key=f"recordings/pmo/{folder}/{name}", size=1000, last_modified=modified
    )


def _names(kept: dict, folder: str) -> list[str]:  # type: ignore[type-arg]
    return [t.obj.key.rsplit("/", 1)[-1] for t in kept[f"recordings/pmo/{folder}/"]]


class TestKeepRecent:
    def test_folder_with_only_older_calls_is_left_out(self) -> None:
        grouped = {
            "recordings/pmo/old/": [_obj("old", "Recording 2026-05-01 10-00-00.webm")]
        }
        assert keep_recent(grouped, EARLIEST, LONDON) == {}

    def test_ongoing_room_keeps_only_its_recent_calls(self) -> None:
        grouped = {
            "recordings/pmo/room/": [
                _obj("room", "Recording 2026-06-30 10-00-00.webm"),
                _obj("room", "Recording 2026-08-04 10-00-00.webm"),
                _obj("room", "Recording 2026-09-29 10-00-00.webm"),
            ]
        }
        kept = keep_recent(grouped, EARLIEST, LONDON)
        assert _names(kept, "room") == [
            "Recording 2026-08-04 10-00-00.webm",
            "Recording 2026-09-29 10-00-00.webm",
        ]
        assert kept["recordings/pmo/room/"][0].recorded_at == datetime(
            2026, 8, 4, 9, 0, tzinfo=UTC
        )

    def test_the_cutoff_is_a_uk_day(self) -> None:
        # 00:30 on 24 July in London is 23:30 UTC on the 23rd: kept. 23:30 on
        # the 23rd in London is before the cutoff: left out.
        grouped = {
            "recordings/pmo/edge/": [
                _obj("edge", "Recording 2026-07-24 00-30-00.webm"),
                _obj("edge", "Recording 2026-07-23 23-30-00.webm"),
            ]
        }
        assert _names(keep_recent(grouped, EARLIEST, LONDON), "edge") == [
            "Recording 2026-07-24 00-30-00.webm"
        ]

    def test_file_without_a_time_uses_its_s3_time(self) -> None:
        grouped = {
            "recordings/pmo/odd/": [
                _obj("odd", "Mani 2.webm", datetime(2026, 9, 1, 9, 0, tzinfo=UTC)),
                _obj("odd", "notes.webm", datetime(2026, 7, 1, 9, 0, tzinfo=UTC)),
            ]
        }
        kept = keep_recent(grouped, EARLIEST, LONDON)
        assert _names(kept, "odd") == ["Mani 2.webm"]
        assert kept["recordings/pmo/odd/"][0].recorded_at is None

    def test_no_cutoff_keeps_every_folder_with_a_recording(self) -> None:
        grouped = {
            "recordings/pmo/old/": [_obj("old", "Recording 2024-01-01 10-00-00.webm")],
            "recordings/pmo/empty/": [],
        }
        kept = keep_recent(grouped, None, LONDON)
        assert list(kept) == ["recordings/pmo/old/"]
