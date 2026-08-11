from src.content.adapters import LinkedInContentAdapter, XContentAdapter


def test_linkedin_adapter_uses_readable_paragraphs() -> None:
    output = LinkedInContentAdapter().fallback(
        "Evidence should survive the writing pipeline.",
        ["Every factual statement points back to a supported claim."],
    )

    assert "\n\n" in output
    assert output.endswith("What would you add or challenge?")


def test_x_adapter_builds_a_native_numbered_thread_without_truncation() -> None:
    thesis = "A short thesis about evidence-first content."
    long_claim = " ".join(["inspectable"] * 80)
    output = XContentAdapter().fallback(thesis, [long_claim])

    posts = output.split("\n\n")
    assert len(posts) > 2
    assert posts[0].startswith(f"1/{len(posts)} ")
    assert posts[-1].startswith(f"{len(posts)}/{len(posts)} ")
    assert output.count("inspectable") == 80
