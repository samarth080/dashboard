"""FIX 6: nothing previously checked that MockLLM actually satisfies LLMClient.

This assignment is a static check: if MockLLM's method signatures drift from
the LLMClient Protocol, pyright fails this line even though it does nothing
interesting at runtime. See the task report for what happens when a MockLLM
method is deliberately broken.
"""

from src.llm.embeddings import EmbeddingProvider, MockEmbedder
from src.llm.mock import MockLLM
from src.llm.protocol import LLMClient


def test_mock_llm_satisfies_protocol() -> None:
    client: LLMClient = MockLLM()
    assert client is not None


def test_mock_embedder_satisfies_protocol() -> None:
    """Same gap, same fix, for EmbeddingProvider.

    No consumer annotates a parameter as `EmbeddingProvider` yet, so nothing
    else in the suite or in pyright's ordinary run would catch MockEmbedder's
    method signatures drifting from the protocol. This assignment is that
    check: pyright fails it if `embed()` or `model` stop matching.
    """
    provider: EmbeddingProvider = MockEmbedder()
    assert provider is not None
