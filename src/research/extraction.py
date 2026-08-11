"""Structured, source-grounded topic extraction behind the shared LLM contract."""

from collections.abc import Sequence

from src.brain.models import Interest
from src.llm.prompts import load_prompt
from src.llm.protocol import LLMClient, StructuredResult
from src.research.models import RawDocument
from src.research.schemas import TopicExtractionOutput

TOPIC_EXTRACTION_PROMPT_NAME = "research-topic-extraction"
TOPIC_EXTRACTION_PROMPT_VERSION = "v1"
MAX_EXTRACTION_CHARACTERS = 100_000
MAX_EXTRACTION_DOCUMENTS = 20


class TopicExtractor:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def extract(
        self,
        documents: Sequence[RawDocument],
        interests: Sequence[Interest],
    ) -> StructuredResult[TopicExtractionOutput]:
        if not documents:
            raise ValueError("at least one canonical document is required")
        if len(documents) > MAX_EXTRACTION_DOCUMENTS:
            raise ValueError(
                f"at most {MAX_EXTRACTION_DOCUMENTS} documents can be extracted at once"
            )

        document_parts: list[str] = []
        current_size = 0
        for document in documents:
            header = f"--- DOCUMENT {document.id} ---\nTITLE: {document.title}\nCONTENT:\n"
            remaining = MAX_EXTRACTION_CHARACTERS - current_size - len(header)
            if remaining <= 0:
                break
            content = document.content[:remaining]
            part = f"{header}{content}"
            document_parts.append(part)
            current_size += len(part)

        if len(document_parts) != len(documents):
            raise ValueError(f"combined documents exceed {MAX_EXTRACTION_CHARACTERS:,} characters")
        interest_text = ", ".join(interest.name for interest in interests if interest.enabled)
        template = load_prompt(TOPIC_EXTRACTION_PROMPT_NAME, TOPIC_EXTRACTION_PROMPT_VERSION)
        if template.count("{{INTERESTS}}") != 1 or template.count("{{DOCUMENTS}}") != 1:
            raise RuntimeError("research extraction prompt markers are invalid")
        prompt = template.replace("{{INTERESTS}}", interest_text or "None configured")
        prompt = prompt.replace("{{DOCUMENTS}}", "\n\n".join(document_parts))
        return await self._llm.structured(
            prompt,
            prompt_version=(f"{TOPIC_EXTRACTION_PROMPT_NAME}/{TOPIC_EXTRACTION_PROMPT_VERSION}"),
            schema=TopicExtractionOutput,
        )
