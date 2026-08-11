"""Explainable deterministic checks used by the M3 AI-slop detector."""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_WORDS = re.compile(r"[A-Za-z0-9']+")
_SENTENCES = re.compile(r"[^.!?]+[.!?]?")
_CLICHES = (
    "in today's fast-paced world",
    "game changer",
    "unlock the power",
    "delve into",
    "revolutionize",
    "ever-evolving landscape",
    "it's not just about",
    "here's the thing",
    "let that sink in",
)


def _score(value: float) -> Decimal:
    bounded = min(1.0, max(0.0, value))
    return Decimal(str(bounded)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DeterministicQualityResult:
    score: Decimal
    subscores: dict[str, Decimal]
    explanations: list[str]


def evaluate_deterministic_quality(
    content: str, *, grounded_claim_count: int
) -> DeterministicQualityResult:
    words = [word.casefold() for word in _WORDS.findall(content)]
    unique_ratio = len(set(words)) / len(words) if words else 0.0
    lexical_diversity = _score(unique_ratio * 1.8)

    sentence_lengths = [
        len(_WORDS.findall(sentence))
        for sentence in _SENTENCES.findall(content)
        if _WORDS.search(sentence)
    ]
    if len(sentence_lengths) < 2:
        sentence_rhythm = _score(0.5)
    else:
        mean = sum(sentence_lengths) / len(sentence_lengths)
        spread = sum(abs(length - mean) for length in sentence_lengths) / len(sentence_lengths)
        sentence_rhythm = _score(0.45 + min(0.55, spread / max(mean, 1)))

    hashtags = len(re.findall(r"(?<!\w)#\w+", content))
    all_caps = len(re.findall(r"\b[A-Z]{5,}\b", content))
    formatting_restraint = _score(1 - max(0, hashtags - 3) * 0.12 - all_caps * 0.08)

    lowered = content.casefold()
    cliche_hits = [phrase for phrase in _CLICHES if phrase in lowered]
    cliche_avoidance = _score(1 - len(cliche_hits) * 0.18)

    number_signal = 0.2 if re.search(r"\b\d+(?:\.\d+)?%?\b", content) else 0.0
    evidence_signal = min(0.8, grounded_claim_count * 0.25)
    specificity = _score(number_signal + evidence_signal)

    subscores = {
        "specificity": specificity,
        "lexical_diversity": lexical_diversity,
        "sentence_rhythm": sentence_rhythm,
        "formatting_restraint": formatting_restraint,
        "cliche_avoidance": cliche_avoidance,
    }
    score = (sum(subscores.values(), start=Decimal("0")) / Decimal(len(subscores))).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )
    explanations = [
        f"Specificity uses {grounded_claim_count} grounded claim reference(s).",
        f"Lexical diversity is based on {len(set(words))} unique tokens across {len(words)} words.",
        f"Sentence rhythm uses {len(sentence_lengths)} sentence(s).",
        f"Formatting contains {hashtags} hashtag(s) and {all_caps} all-caps token(s).",
        (
            "No configured AI-writing clichés were detected."
            if not cliche_hits
            else "Detected cliché phrase(s): " + ", ".join(cliche_hits) + "."
        ),
    ]
    return DeterministicQualityResult(score=score, subscores=subscores, explanations=explanations)
