from app.skills.ship30 import validate_essay


def _build_good_essay(target_words: int = 1250) -> str:
    header = (
        "# The Activation Trap\n\n"
        "## Why acquisition wins the argument\n\n"
        "- It shows up in a dashboard\n- It has a clean attribution story\n- It feels like progress\n\n"
        "## What Elena Verna actually found\n\n"
        "**Activation, not acquisition, is the real lever** for durable growth.\n\n"
        "## The takeaway\n\nAudit your activation funnel this week before you touch acquisition spend again.\n\n"
    )
    filler_needed = target_words - len(header.split())
    body = " ".join(["word"] * max(filler_needed, 0))
    return header + body


GOOD_ESSAY = _build_good_essay(1250)

BAD_ESSAY = "just a short paragraph with no structure at all and no emphasis whatsoever."


def test_good_essay_passes_validation():
    result = validate_essay(GOOD_ESSAY, target_words=1250)
    assert result.ok, result.issues


def test_bad_essay_flags_missing_heading_bullets_and_bold():
    result = validate_essay(BAD_ESSAY, target_words=1250)
    assert not result.ok
    assert any("heading" in issue for issue in result.issues)
    assert any("bullet" in issue for issue in result.issues)
    assert any("bold" in issue for issue in result.issues)
    assert any("word count" in issue for issue in result.issues)


def test_word_count_outside_tolerance_is_flagged_even_with_good_formatting():
    short_but_formatted = "# Title\n\n**Bold claim.**\n\n- one\n- two\n\nShort essay."
    result = validate_essay(short_but_formatted, target_words=1250)
    assert not result.ok
    assert any("word count" in issue for issue in result.issues)


def test_word_count_within_tolerance_passes():
    words = " ".join(["word"] * 1250)
    essay = f"# Title\n\n**Important.**\n\n- a\n- b\n\n{words}"
    result = validate_essay(essay, target_words=1250)
    assert result.word_count > 1250  # extra words from title/bullets are fine
    assert all("word count" not in issue for issue in result.issues)


def test_bullet_character_bullets_are_recognized():
    # Found live against a real local model, which used "•" bullets instead
    # of Markdown "-"/"*" — genuinely skimmable formatting that the original
    # regex didn't recognize as a bullet list at all.
    words = " ".join(["word"] * 1250)
    essay = f"# Title\n\n**Important.**\n\n• one\n• two\n\n{words}"
    result = validate_essay(essay, target_words=1250)
    assert not any("bullet" in issue for issue in result.issues)
