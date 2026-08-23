from app.services.chunker import chunk_transcript

SAMPLE = """**Lenny Rachitsky** (00:00:00):
Welcome to the show. Today we're talking about growth loops and retention.

**Elena Verna** (00:00:10):
Thanks for having me. The single biggest lever for B2B growth is almost always
activation, not acquisition. Most teams over-invest in the top of the funnel.

**Lenny Rachitsky** (00:00:30):
Why do you think that happens?

**Elena Verna** (00:00:35):
Because acquisition is easy to attribute and easy to show a chart about.
Activation work is messier and slower to show up in a dashboard.
"""


def test_splits_on_speaker_turns():
    chunks = chunk_transcript(SAMPLE, target_tokens=1000, overlap_tokens=10)
    assert len(chunks) == 1  # small transcript, big budget -> one chunk
    assert "Elena Verna" in chunks[0].content
    assert chunks[0].start_speaker == "Lenny Rachitsky"


def test_respects_small_token_budget_by_splitting_into_multiple_chunks():
    chunks = chunk_transcript(SAMPLE, target_tokens=15, overlap_tokens=5)
    assert len(chunks) > 1
    # every chunk should be non-empty and carry a token count
    assert all(c.token_count > 0 for c in chunks)


def test_chunk_indices_are_sequential():
    chunks = chunk_transcript(SAMPLE, target_tokens=15, overlap_tokens=5)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_falls_back_to_paragraph_split_for_unstructured_text():
    body = "First paragraph about pricing.\n\nSecond paragraph about churn.\n\nThird about NRR."
    chunks = chunk_transcript(body, target_tokens=1000, overlap_tokens=10)
    assert len(chunks) == 1
    assert "pricing" in chunks[0].content and "NRR" in chunks[0].content


def test_empty_body_returns_no_chunks():
    assert chunk_transcript("", target_tokens=200, overlap_tokens=20) == []
