"""Deterministic, credential-free `LLMClient` implementation.

Exists so complete workflows can be exercised in tests and local dev without
API keys — including ones that call `structured()` with real, required-field
schemas. Both the returned response and the (fake) latency can be pinned via
the constructor for tests that need to assert on a specific value.
"""

from decimal import Decimal
from types import UnionType
from typing import Union, get_args, get_origin

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from src.llm.protocol import LLMResult, StructuredResult


def _build_placeholder(field_name: str, annotation: object) -> object:
    """Produce a type-appropriate placeholder value for a field with no default."""
    origin = get_origin(annotation)

    if origin in (Union, UnionType):
        args = get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) < len(args):
            # Optional[...] (or `X | None`) — None always satisfies it.
            return None
        return _build_placeholder(field_name, non_none[0])

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _deterministic_instance(annotation)

    if annotation is str:
        return field_name
    if annotation is bool:
        return False
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is list or origin is list:
        return []
    if annotation is dict or origin is dict:
        return {}

    raise TypeError(
        f"MockLLM cannot build a placeholder value for field {field_name!r} of type "
        f"{annotation!r}. Pass an explicit structured_response=... to MockLLM instead."
    )


def _deterministic_instance[T: BaseModel](schema: type[T]) -> T:
    """Build a valid instance of `schema`, using field defaults where present
    and a type-appropriate placeholder everywhere else (recursing into
    nested models). This is a test double, not a fuzzer: values are fixed
    and predictable, not randomized.
    """
    values: dict[str, object] = {}
    for name, field in schema.model_fields.items():
        if field.default is not PydanticUndefined:
            values[name] = field.default
        elif field.default_factory is not None:
            values[name] = field.default_factory()  # type: ignore[call-arg]
        else:
            values[name] = _build_placeholder(name, field.annotation)
    return schema(**values)


class MockLLM:
    model_name = "mock-llm"

    def __init__(
        self,
        *,
        structured_response: BaseModel | None = None,
        latency_ms: int = 0,
    ) -> None:
        """
        structured_response: if given, `structured()` always returns this
            exact object instead of building a deterministic instance. It is
            the caller's responsibility to pass an instance matching the
            `schema` that will be requested.
        latency_ms: fixed value reported as latency on every result. Real
            providers measure this; a mock has nothing to measure, so it is
            injectable for tests that assert on latency rather than fabricated.
        """
        self._structured_response = structured_response
        self._latency_ms = latency_ms

    async def generate(self, prompt: str, *, prompt_version: str) -> LLMResult:
        text = f"[mock response to: {prompt[:50]}]"
        return LLMResult(
            text=text,
            model=self.model_name,
            prompt_version=prompt_version,
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            latency_ms=self._latency_ms,
            cost_usd=Decimal("0"),
        )

    async def structured[T: BaseModel](
        self, prompt: str, *, prompt_version: str, schema: type[T]
    ) -> StructuredResult[T]:
        if self._structured_response is not None:
            # Caller's contract: the injected response must match `schema`.
            parsed: T = self._structured_response  # type: ignore[assignment]
        else:
            parsed = _deterministic_instance(schema)

        text = parsed.model_dump_json()
        usage = LLMResult(
            text=text,
            model=self.model_name,
            prompt_version=prompt_version,
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            latency_ms=self._latency_ms,
            cost_usd=Decimal("0"),
        )
        return StructuredResult(parsed=parsed, usage=usage)
