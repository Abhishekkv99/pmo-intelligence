"""One structured-output call to the chat model, with its token usage.

Every pipeline node asks for a Pydantic model (``method="json_schema"``) and
reads the token counts from the raw message, so the call can be costed. A
reply that does not parse raises, and the node wrapper records it.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.ai.llm_factory import build_chat_llm


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int


class StructuredOutputError(Exception):
    """The model's reply did not match the requested schema."""


async def invoke_structured[ModelT: BaseModel](
    schema: type[ModelT], system: str, user: str, *, reasoning_effort: str
) -> tuple[ModelT, LLMUsage]:
    llm = build_chat_llm(reasoning_effort)
    structured = llm.with_structured_output(
        schema, method="json_schema", include_raw=True
    )
    reply: dict[str, Any] = await structured.ainvoke(
        [{"role": "system", "content": system}, {"role": "user", "content": user}]
    )
    parsed = reply.get("parsed")
    if not isinstance(parsed, schema):
        error = reply.get("parsing_error")
        raise StructuredOutputError(
            f"The reply did not match {schema.__name__}: {error or 'no content'}"
        )
    usage = getattr(reply.get("raw"), "usage_metadata", None) or {}
    return parsed, LLMUsage(
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
    )
