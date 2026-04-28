import json
from pathlib import Path
from mind.extractors.copilot import CopilotExtractor


def _make_events_file(session_dir: Path, cwd: str, messages: list[dict]) -> None:
    session_dir.mkdir(parents=True)
    events_file = session_dir / "events.jsonl"
    lines = []
    lines.append(json.dumps({"type": "session.start", "data": {"cwd": cwd}}))
    for msg in messages:
        role = msg["role"]
        event_type = "user.message" if role == "user" else "assistant.message"
        lines.append(json.dumps({
            "type": event_type,
            "timestamp": "2024-01-01T00:00:00Z",
            "data": {"content": msg["content"]},
        }))
    events_file.write_text("\n".join(lines) + "\n")


def test_extracts_copilot_messages(tmp_path):
    session_dir = tmp_path / "session-abc123"
    _make_events_file(session_dir, "/home/ubuntu/cvt-scanner", [
        {"role": "user", "content": "explain the egress guard"},
        {"role": "assistant", "content": "The egress guard is..."},
    ])
    extractor = CopilotExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500, project_path="/home/ubuntu/cvt-scanner")
    assert any(m.role == "user" for m in messages)
    assert any(m.role == "assistant" for m in messages)


def test_ignores_workspace_for_different_project(tmp_path):
    session_dir = tmp_path / "session-xyz"
    _make_events_file(session_dir, "/home/ubuntu/other-project", [
        {"role": "user", "content": "hello from other project"},
    ])
    extractor = CopilotExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500, project_path="/home/ubuntu/cvt-scanner")
    assert messages == []


def test_excludes_session_with_empty_cwd_when_project_path_set(tmp_path):
    """Sessions where cwd cannot be read should be excluded when project_path is set (Bug 3 fix)."""
    session_dir = tmp_path / "session-nocwd"
    session_dir.mkdir(parents=True)
    events_file = session_dir / "events.jsonl"
    # No session.start event — cwd will be empty
    events_file.write_text(json.dumps({
        "type": "user.message",
        "timestamp": "2024-01-01T00:00:00Z",
        "data": {"content": "some message from unknown project"},
    }) + "\n")
    extractor = CopilotExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500, project_path="/home/ubuntu/cvt-scanner")
    assert messages == []


def test_includes_session_with_empty_cwd_when_no_project_filter(tmp_path):
    """Without a project_path filter, sessions with empty cwd should still be included."""
    session_dir = tmp_path / "session-nocwd"
    session_dir.mkdir(parents=True)
    events_file = session_dir / "events.jsonl"
    events_file.write_text(json.dumps({
        "type": "user.message",
        "timestamp": "2024-01-01T00:00:00Z",
        "data": {"content": "some message from unknown project"},
    }) + "\n")
    extractor = CopilotExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500, project_path="")
    assert any("unknown project" in m.text for m in messages)
