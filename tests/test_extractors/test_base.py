from mind.extractors.base import Message


def test_message_fields():
    m = Message(role="user", text="hello", timestamp="2026-04-18T10:00:00Z", tool="claude")
    assert m.role == "user"
    assert m.text == "hello"
    assert m.timestamp == "2026-04-18T10:00:00Z"
    assert m.tool == "claude"


def test_message_truncate():
    long_text = "x" * 1000
    m = Message(role="user", text=long_text, timestamp="2026-04-18T10:00:00Z", tool="claude")
    assert len(m.truncated(500)) <= 500


def test_message_format():
    m = Message(role="user", text="fix this", timestamp="2026-04-18T10:00:00Z", tool="claude")
    assert m.format() == "[USER]: fix this"
