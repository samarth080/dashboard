"""Voice analysis workflow built on versioned prompts and `LLMClient`."""

from collections.abc import Sequence

from src.brain.schemas import VoiceAnalysis
from src.llm.prompts import load_prompt
from src.llm.protocol import LLMClient, StructuredResult

VOICE_PROMPT_NAME = "voice-analysis"
VOICE_PROMPT_VERSION = "v1"
MAX_ANALYSIS_CHARACTERS = 100_000


class VoiceAnalyzer:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def analyze(self, samples: Sequence[str]) -> StructuredResult[VoiceAnalysis]:
        if not samples:
            raise ValueError("at least one confirmed writing sample is required")

        sample_block = "\n\n".join(
            f"--- SAMPLE {index} ---\n{sample}" for index, sample in enumerate(samples, start=1)
        )
        if len(sample_block) > MAX_ANALYSIS_CHARACTERS:
            raise ValueError(
                f"combined writing samples exceed {MAX_ANALYSIS_CHARACTERS:,} characters"
            )

        template = load_prompt(VOICE_PROMPT_NAME, VOICE_PROMPT_VERSION)
        marker = "{{WRITING_SAMPLES}}"
        if template.count(marker) != 1:
            raise RuntimeError(f"voice prompt must contain exactly one {marker} marker")
        prompt = template.replace(marker, sample_block)
        return await self._llm.structured(
            prompt,
            prompt_version=f"{VOICE_PROMPT_NAME}/{VOICE_PROMPT_VERSION}",
            schema=VoiceAnalysis,
        )
