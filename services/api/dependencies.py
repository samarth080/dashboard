"""Shared FastAPI dependency providers."""

from fastapi import Request

from src.llm.embeddings import EmbeddingProvider
from src.llm.protocol import LLMClient


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client


def get_embedder(request: Request) -> EmbeddingProvider:
    return request.app.state.embedder
