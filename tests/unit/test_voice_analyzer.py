import pytest

from src.brain.schemas import VoiceAnalysis
from src.brain.voice import VoiceAnalyzer
from src.llm.mock import MockLLM


@pytest.mark.asyncio
async def test_voice_analyzer_requires_at_least_one_sample() -> None:
    with pytest.raises(ValueError, match="at least one"):
        await VoiceAnalyzer(MockLLM()).analyze([])


@pytest.mark.asyncio
async def test_voice_analyzer_uses_versioned_prompt_and_structured_result() -> None:
    canned = VoiceAnalysis(
        summary="Direct, practical, and example-led.",
        tone_descriptors=["direct", "warm"],
        sentence_patterns=["short opening"],
        vocabulary_preferences=["plain language"],
        avoid_phrases=["game changer"],
        formatting_preferences=["short paragraphs"],
        signature_traits=["concrete examples"],
        confidence=0.8,
    )
    result = await VoiceAnalyzer(MockLLM(structured_response=canned)).analyze(
        ["A sufficiently detailed sample that shows how this person normally explains an idea."]
    )
    assert result.parsed is canned
    assert result.usage.prompt_version == "voice-analysis/v1"
    assert result.usage.input_tokens > 0
