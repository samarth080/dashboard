import pytest

from src.llm.prompts import load_prompt


def test_voice_prompt_loads_by_version() -> None:
    prompt = load_prompt("voice-analysis", "v1")
    assert "{{WRITING_SAMPLES}}" in prompt
    assert "do not infer demographics" in prompt


def test_prompt_registry_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        load_prompt("../voice-analysis", "v1")
