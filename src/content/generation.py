"""Versioned structured model calls for explicit Content Engine stages."""

import json

from src.content.schemas import GeneratedContent, ModelQualityJudgement
from src.llm.prompts import load_prompt
from src.llm.protocol import LLMClient, StructuredResult

PROMPT_VERSION = "v1"
STAGE_PROMPTS = {
    "angle": "content-angle",
    "outline": "content-outline",
    "draft": "content-draft",
    "voice_transform": "content-voice-transform",
    "rewrite": "content-rewrite",
    "linkedin_adaptation": "content-linkedin-adaptation",
    "x_adaptation": "content-x-adaptation",
}
QUALITY_PROMPT_NAME = "content-quality-evaluation"


def prompt_version(name: str) -> str:
    return f"{name}/{PROMPT_VERSION}"


def _render(name: str, context: dict[str, object]) -> str:
    template = load_prompt(name, PROMPT_VERSION)
    marker = "{{CONTEXT}}"
    if template.count(marker) != 1:
        raise RuntimeError(f"content prompt must contain exactly one {marker} marker")
    return template.replace(marker, json.dumps(context, ensure_ascii=False, indent=2, default=str))


class ContentGenerator:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def generate(
        self, stage: str, context: dict[str, object]
    ) -> StructuredResult[GeneratedContent]:
        name = STAGE_PROMPTS[stage]
        return await self._llm.structured(
            _render(name, context),
            prompt_version=prompt_version(name),
            schema=GeneratedContent,
        )

    async def evaluate_quality(
        self, context: dict[str, object]
    ) -> StructuredResult[ModelQualityJudgement]:
        return await self._llm.structured(
            _render(QUALITY_PROMPT_NAME, context),
            prompt_version=prompt_version(QUALITY_PROMPT_NAME),
            schema=ModelQualityJudgement,
        )
