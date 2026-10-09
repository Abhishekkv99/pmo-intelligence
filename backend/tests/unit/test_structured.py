"""One structured-output call: the parsed answer and its token usage."""

from typing import Any

import pytest
from pydantic import BaseModel

from app.ai import structured
from app.ai.structured import StructuredOutputError, invoke_structured


class Answer(BaseModel):
    text: str


class Raw:
    usage_metadata = {"input_tokens": 1_200, "output_tokens": 80}


class FakeRunnable:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.messages: list[dict[str, str]] = []

    async def ainvoke(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        self.messages = messages
        return self.reply


class FakeLLM:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.runnable = FakeRunnable(reply)
        self.calls: list[tuple[type[BaseModel], dict[str, Any]]] = []

    def with_structured_output(
        self, schema: type[BaseModel], **kwargs: Any
    ) -> FakeRunnable:
        self.calls.append((schema, kwargs))
        return self.runnable


def _use(
    monkeypatch: pytest.MonkeyPatch, reply: dict[str, Any]
) -> tuple[FakeLLM, list[str]]:
    llm = FakeLLM(reply)
    efforts: list[str] = []

    def build(reasoning_effort: str = "medium") -> FakeLLM:
        efforts.append(reasoning_effort)
        return llm

    monkeypatch.setattr(structured, "build_chat_llm", build)
    return llm, efforts


async def test_the_parsed_answer_and_token_usage_are_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, efforts = _use(monkeypatch, {"parsed": Answer(text="hi"), "raw": Raw()})

    answer, usage = await invoke_structured(
        Answer, "system text", "user text", reasoning_effort="low"
    )

    assert answer == Answer(text="hi")
    assert (usage.input_tokens, usage.output_tokens) == (1_200, 80)
    assert efforts == ["low"]
    assert llm.calls == [(Answer, {"method": "json_schema", "include_raw": True})]
    assert llm.runnable.messages == [
        {"role": "system", "content": "system text"},
        {"role": "user", "content": "user text"},
    ]


async def test_a_reply_that_does_not_parse_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, {"parsed": None, "parsing_error": "bad json", "raw": Raw()})

    with pytest.raises(StructuredOutputError, match="bad json"):
        await invoke_structured(Answer, "s", "u", reasoning_effort="medium")


async def test_missing_usage_counts_as_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, {"parsed": Answer(text="hi"), "raw": object()})

    _, usage = await invoke_structured(Answer, "s", "u", reasoning_effort="medium")

    assert (usage.input_tokens, usage.output_tokens) == (0, 0)
