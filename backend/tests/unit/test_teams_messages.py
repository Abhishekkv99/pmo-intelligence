"""Teams message bodies as text, Graph messages as stored rows, and the reads
the sync asks Graph for. Message text is made up."""

from datetime import UTC, datetime, timedelta, timezone

import httpx

from app.services.teams.graph_client import GraphClient
from app.services.teams.message_text import html_to_text, message_text
from app.services.teams.messages import (
    GraphMessageSource,
    graph_time,
    parse_time,
    read_message,
)


class TestHtmlToText:
    def test_paragraphs_and_breaks_become_lines(self) -> None:
        assert (
            html_to_text("<p>Hi all,</p><p>Sprint demo done.<br>Next: tests</p>")
            == "Hi all,\n\nSprint demo done.\nNext: tests"
        )

    def test_a_mention_keeps_the_name_and_entities_are_decoded(self) -> None:
        assert (
            html_to_text('<p><at id="0">Pat Manager</at> R&amp;D &gt; 2 days</p>')
            == "Pat Manager R&D > 2 days"
        )

    def test_emoji_images_and_attachments(self) -> None:
        html = (
            '<p>Done <emoji id="1" alt="👍" title="Like"></emoji></p>'
            '<img alt="diagram" src="x"><attachment id="abc"></attachment>'
        )
        assert html_to_text(html) == "Done 👍\n[image: diagram][attachment]"

    def test_list_items_are_bulleted_and_spaces_collapsed(self) -> None:
        assert (
            html_to_text("<ul><li>one&nbsp;&nbsp; thing</li><li>two</li></ul>")
            == "- one thing\n- two"
        )

    def test_style_and_script_are_dropped(self) -> None:
        assert html_to_text("<style>p{}</style><p>text</p><script>x()</script>") == (
            "text"
        )

    def test_message_text_reads_html_and_plain_bodies(self) -> None:
        assert message_text({"contentType": "html", "content": "<p>a</p>"}) == "a"
        assert message_text({"contentType": "text", "content": " a  b "}) == "a b"
        assert message_text(None) == ""
        assert message_text({"contentType": "html", "content": None}) == ""


def _item(**fields: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": "1700000000001",
        "messageType": "message",
        "createdDateTime": "2026-11-17T09:00:00.123Z",
        "lastModifiedDateTime": "2026-11-17T09:00:00.123Z",
        "deletedDateTime": None,
        "from": {"user": {"id": "oid-1", "displayName": "Alex Sample"}},
        "body": {"contentType": "html", "content": "<p>Blocked on access</p>"},
    }
    item.update(fields)
    return item


class TestReadMessage:
    def test_reads_a_message(self) -> None:
        message = read_message(_item())
        assert message is not None
        assert message.graph_id == "1700000000001"
        assert message.posted_at == datetime(2026, 11, 17, 9, 0, 0, 123000, UTC)
        assert message.author_oid == "oid-1"
        assert message.author_name == "Alex Sample"
        assert message.body_text == "Blocked on access"
        assert message.deleted_at is None

    def test_a_deleted_message_has_no_text_and_its_change_time(self) -> None:
        message = read_message(
            _item(
                lastModifiedDateTime="2026-11-17T09:00:00Z",
                deletedDateTime="2026-11-17T10:00:00Z",
            )
        )
        assert message is not None
        assert message.body_text == ""
        assert message.deleted_at == datetime(2026, 11, 17, 10, tzinfo=UTC)
        assert message.last_modified_at == message.deleted_at

    def test_a_system_event_has_no_author(self) -> None:
        message = read_message(
            _item(
                messageType="systemEventMessage",
                **{"from": None},
                body={"contentType": "html", "content": "<systemEventMessage/>"},
            )
        )
        assert message is not None
        assert message.message_type == "systemEventMessage"
        assert message.author_oid is None and message.author_name is None

    def test_an_item_without_id_or_time_is_skipped(self) -> None:
        assert read_message(_item(id=None)) is None
        assert read_message(_item(createdDateTime="not a time")) is None


class TestTimes:
    def test_graph_time_is_utc_with_milliseconds(self) -> None:
        local = datetime(2026, 11, 17, 15, 30, 5, 678901, timezone(timedelta(hours=5)))
        assert graph_time(local) == "2026-11-17T10:30:05.678Z"

    def test_parse_time_reads_z_and_offsets(self) -> None:
        assert parse_time("2026-11-17T10:00:00Z") == datetime(
            2026, 11, 17, 10, tzinfo=UTC
        )
        assert parse_time(None) is None and parse_time("x") is None


class _Tokens:
    async def token(self) -> str:
        return "t"


class TestGraphMessageSource:
    async def test_changes_are_read_newest_change_first_after_the_watermark(
        self,
    ) -> None:
        seen: list[httpx.URL] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url)
            return httpx.Response(200, json={"value": [{"id": "m1"}]})

        async def no_sleep(_: float) -> None:
            return None

        graph = GraphClient(
            _Tokens(), transport=httpx.MockTransport(handler), sleep=no_sleep
        )
        items = [
            item
            async for item in GraphMessageSource(graph).changed_since(
                "19:abc@thread.v2", datetime(2026, 11, 17, 10, tzinfo=UTC)
            )
        ]
        await graph.aclose()

        assert items == [{"id": "m1"}]
        url = seen[0]
        assert url.path == "/v1.0/chats/19:abc@thread.v2/messages"
        assert url.params["$orderby"] == "lastModifiedDateTime desc"
        assert url.params["$filter"] == (
            "lastModifiedDateTime gt 2026-11-17T10:00:00.000Z"
        )
        assert url.params["$top"] == "50"
