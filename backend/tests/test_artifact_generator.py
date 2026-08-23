from app.artifacts.generator import extract_artifact


def test_extracts_markdown_fence_and_title_from_h1():
    output = "Sure, here you go:\n\n```markdown\n# My Great Doc\n\nBody text here.\n```\n"
    artifact = extract_artifact(output, fallback_title="fallback")
    assert artifact is not None
    assert artifact.kind == "markdown"
    assert artifact.title == "My Great Doc"
    assert "Body text here." in artifact.raw_content
    assert "Sure, here you go" not in artifact.raw_content


def test_extracts_html_fence_and_title_from_title_tag():
    output = '```html\n<html><head><title>Landing Page</title></head><body>Hi</body></html>\n```'
    artifact = extract_artifact(output, fallback_title="fallback")
    assert artifact is not None
    assert artifact.kind == "html"
    assert artifact.title == "Landing Page"


def test_html_fence_is_sanitized():
    output = '```html\n<html><head></head><body><script src="https://evil.example/x.js"></script></body></html>\n```'
    artifact = extract_artifact(output, fallback_title="fallback")
    assert artifact is not None
    assert "evil.example" not in artifact.sanitized_content
    # raw_content preserves what the model actually said, for audit
    assert "evil.example" in artifact.raw_content


def test_markdown_fence_without_title_uses_fallback():
    output = "```markdown\nJust some text, no heading.\n```"
    artifact = extract_artifact(output, fallback_title="My Fallback")
    assert artifact is not None
    assert artifact.title == "My Fallback"


def test_returns_none_when_no_fence_present():
    output = "I didn't follow instructions and just wrote plain text."
    assert extract_artifact(output, fallback_title="x") is None
