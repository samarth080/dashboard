from src.content.quality import evaluate_deterministic_quality


def test_quality_report_has_explainable_bounded_subscores() -> None:
    result = evaluate_deterministic_quality(
        (
            "Evidence provenance changes the review process. Teams can inspect one source "
            "before accepting a conclusion. That makes disagreements concrete, not vague."
        ),
        grounded_claim_count=2,
    )

    assert set(result.subscores) == {
        "specificity",
        "lexical_diversity",
        "sentence_rhythm",
        "formatting_restraint",
        "cliche_avoidance",
    }
    assert all(0 <= score <= 1 for score in result.subscores.values())
    assert 0 <= result.score <= 1
    assert len(result.explanations) == 5


def test_cliches_and_excessive_formatting_reduce_explainable_scores() -> None:
    clean = evaluate_deterministic_quality(
        "A source excerpt makes the claim inspectable. Reviewers can test the conclusion.",
        grounded_claim_count=1,
    )
    noisy = evaluate_deterministic_quality(
        (
            "IN TODAY'S FAST-PACED WORLD this GAME CHANGER will unlock the power. "
            "#ai #growth #future #winning #viral"
        ),
        grounded_claim_count=0,
    )

    assert noisy.subscores["formatting_restraint"] < clean.subscores["formatting_restraint"]
    assert noisy.subscores["cliche_avoidance"] < clean.subscores["cliche_avoidance"]
    assert any("cliché" in explanation for explanation in noisy.explanations)
