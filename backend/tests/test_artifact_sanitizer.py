from app.artifacts.sanitizer import sanitize_html_artifact


def test_strips_remote_script_tag():
    html = '<html><head></head><body><script src="https://evil.example/x.js"></script></body></html>'
    out = sanitize_html_artifact(html)
    assert "evil.example" not in out


def test_keeps_inline_script_tag():
    html = "<html><head></head><body><script>console.log('hi')</script></body></html>"
    out = sanitize_html_artifact(html)
    assert "console.log" in out


def test_strips_base_tag():
    html = '<html><head><base href="https://evil.example/"></head><body></body></html>'
    out = sanitize_html_artifact(html)
    assert "<base" not in out.lower()


def test_strips_meta_refresh():
    html = '<html><head><meta http-equiv="refresh" content="0; url=https://evil.example"></head></html>'
    out = sanitize_html_artifact(html)
    assert "refresh" not in out.lower()


def test_strips_event_handler_attributes():
    html = '<html><body><img src="a.png" onerror="fetch(\'https://evil.example\')"></body></html>'
    out = sanitize_html_artifact(html)
    assert "onerror" not in out.lower()


def test_strips_remote_stylesheet_link():
    html = '<html><head><link rel="stylesheet" href="https://cdn.example/x.css"></head></html>'
    out = sanitize_html_artifact(html)
    assert "cdn.example" not in out


def test_injects_content_security_policy():
    html = "<html><head><title>x</title></head><body>hi</body></html>"
    out = sanitize_html_artifact(html)
    assert "Content-Security-Policy" in out
    assert "connect-src 'none'" in out


def test_handles_html_with_no_head_tag():
    html = "<html><body>hi</body></html>"
    out = sanitize_html_artifact(html)
    assert "Content-Security-Policy" in out


def test_handles_fragment_with_no_html_tag():
    html = "<div>just a fragment</div>"
    out = sanitize_html_artifact(html)
    assert "Content-Security-Policy" in out
    assert "just a fragment" in out
