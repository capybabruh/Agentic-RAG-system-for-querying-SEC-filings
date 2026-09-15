from __future__ import annotations

from app.chat.schemas import AiSdkMessage, MessagePart


def test_text_prefers_content_over_parts():
    message = AiSdkMessage(role="user", content="What changed?", parts=[MessagePart(type="text", text="ignored")])

    assert message.text() == "What changed?"


def test_text_falls_back_to_concatenated_text_parts():
    message = AiSdkMessage(
        role="user",
        parts=[MessagePart(type="text", text="What "), MessagePart(type="text", text="changed?")],
    )

    assert message.text() == "What changed?"


def test_text_ignores_non_text_parts():
    message = AiSdkMessage(
        role="user",
        parts=[
            MessagePart(type="text", text="Look at this: "),
            MessagePart(type="file", text="ignored-file-content"),
        ],
    )

    assert message.text() == "Look at this: "


def test_text_with_no_content_and_no_parts_is_empty_string():
    message = AiSdkMessage(role="user")

    assert message.text() == ""


def test_text_part_with_no_text_field_contributes_nothing():
    message = AiSdkMessage(role="user", parts=[MessagePart(type="text")])

    assert message.text() == ""
