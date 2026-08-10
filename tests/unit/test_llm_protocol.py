"""FIX 6: nothing previously checked that MockLLM actually satisfies LLMClient.

This assignment is a static check: if MockLLM's method signatures drift from
the LLMClient Protocol, pyright fails this line even though it does nothing
interesting at runtime. See the task report for what happens when a MockLLM
method is deliberately broken.
"""

from src.llm.mock import MockLLM
from src.llm.protocol import LLMClient


def test_mock_llm_satisfies_protocol() -> None:
    client: LLMClient = MockLLM()
    assert client is not None
