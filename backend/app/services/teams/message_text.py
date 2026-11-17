"""A Teams message body as plain text.

Graph gives a chat message's body as ``html`` (most) or ``text``. The stored
text keeps what a person reads: paragraphs and line breaks as new lines, a
mention as the name shown, an emoji as its character, an attachment or image
as a placeholder, entities decoded, runs of spaces collapsed. Nothing here
logs the text.
"""

import re
from html.parser import HTMLParser

# Tags that end a line when they open or close.
_BLOCK_TAGS = frozenset(
    {"p", "div", "ul", "ol", "tr", "table", "blockquote", "h1", "h2", "h3"}
)
_SPACES = re.compile(r"[ \t\r\f\v ]+")
_BLANK_LINES = re.compile(r"\n{3,}")


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0  # inside <style> or <script>

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script"):
            self._skip += 1
        elif tag == "br" or tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "emoji":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(alt)
        elif tag == "img":
            alt = dict(attrs).get("alt")
            self.parts.append(f"[image: {alt}]" if alt else "[image]")
        elif tag == "attachment":
            self.parts.append("[attachment]")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _tidy(text: str) -> str:
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def html_to_text(html: str) -> str:
    """The text a person reads in a Teams message's HTML body."""
    collector = _TextCollector()
    collector.feed(html)
    collector.close()
    return _tidy("".join(collector.parts))


def message_text(body: dict[str, object] | None) -> str:
    """A Graph ``itemBody`` (``contentType``, ``content``) as plain text."""
    if not body:
        return ""
    content = body.get("content")
    if not isinstance(content, str) or not content:
        return ""
    if str(body.get("contentType", "")).lower() == "html":
        return html_to_text(content)
    return _tidy(content)
