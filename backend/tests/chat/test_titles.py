from __future__ import annotations

from app.chat.titles import derive_thread_title


def test_derive_thread_title_returns_short_text_unchanged():
    assert derive_thread_title("What was Apple's revenue?") == "What was Apple's revenue?"


def test_derive_thread_title_collapses_internal_whitespace():
    assert derive_thread_title("What   was\n\nApple's revenue?") == "What was Apple's revenue?"


def test_derive_thread_title_truncates_long_text_at_a_word_boundary():
    text = "What was Apple's total revenue growth across all reportable segments in fiscal year 2024?"

    title = derive_thread_title(text)

    assert len(title) <= 61
    assert title.endswith("…")
    assert not title.endswith(" …")
    assert text.startswith(title.removesuffix("…").rstrip())


def test_derive_thread_title_strips_trailing_punctuation_before_ellipsis():
    text = "x" * 65 + "."

    assert derive_thread_title(text) == "x" * 60 + "…"
