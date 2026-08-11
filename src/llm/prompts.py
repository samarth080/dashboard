"""Small, path-safe registry for versioned prompt files."""

import re
from pathlib import Path

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"
_SAFE_COMPONENT = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def load_prompt(name: str, version: str) -> str:
    """Load an immutable prompt by logical name and version.

    Both components are restricted so caller input can never traverse outside
    the prompt registry. Missing prompts fail loudly instead of silently
    falling back to an unversioned string.
    """
    if not _SAFE_COMPONENT.fullmatch(name) or not _SAFE_COMPONENT.fullmatch(version):
        raise ValueError(
            "prompt name and version must contain lowercase letters, digits, or hyphens"
        )
    path = PROMPTS_ROOT / name / f"{version}.md"
    return path.read_text(encoding="utf-8").strip()
