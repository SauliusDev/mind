import json
from pathlib import Path
from mind.extractors.codex import CodexExtractor


def _make_rollout(directory: Path, filename: str, cwd: str, entries: list[dict]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    rollout = directory / filename
    lines = []
    if cwd:
        lines.append(json.dumps({"type": "session_meta", "payload": {"cwd": cwd}}))
    for entry in entries:
        lines.append(json.dumps(entry))
    rollout.write_text("\n".join(lines) + "\n")
    return rollout


def test_extracts_from_rollout_jsonl(tmp_path):
    _make_rollout(tmp_path, "rollout-001.jsonl", "/home/ubuntu/myproject", [
        {"type": "event_msg", "timestamp": "2024-01-01T00:00:00Z",
         "payload": {"type": "user_message", "message": "fix the validator timeout"}},
        {"type": "event_msg", "timestamp": "2024-01-01T00:00:01Z",
         "payload": {"type": "agent_message", "phase": "final", "message": "here is the fix I applied"}},
    ])
    extractor = CodexExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500)
    assert len(messages) >= 1
    assert any("validator" in m.text for m in messages)


def test_skips_unchanged_rollout(tmp_path):
    rollout = _make_rollout(tmp_path, "rollout-001.jsonl", "/home/ubuntu/myproject", [
        {"type": "event_msg", "timestamp": "2024-01-01T00:00:00Z",
         "payload": {"type": "user_message", "message": "hello"}},
    ])
    from datetime import datetime, timezone
    mtime = datetime.fromtimestamp(rollout.stat().st_mtime, tz=timezone.utc).isoformat()
    extractor = CodexExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={"rollout-001.jsonl": mtime}, max_chars=500)
    assert messages == []


def test_excludes_session_with_empty_cwd_when_project_path_set(tmp_path):
    """Sessions where cwd cannot be read should be excluded when project_path is set (Bug 3 fix)."""
    _make_rollout(tmp_path, "rollout-nocwd.jsonl", "", [
        {"type": "event_msg", "timestamp": "2024-01-01T00:00:00Z",
         "payload": {"type": "user_message", "message": "message from unknown project"}},
    ])
    extractor = CodexExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500, project_path="/home/ubuntu/myproject")
    assert messages == []


def test_includes_session_with_empty_cwd_when_no_project_filter(tmp_path):
    """Without a project_path filter, all sessions should be included regardless of cwd."""
    _make_rollout(tmp_path, "rollout-nocwd.jsonl", "", [
        {"type": "event_msg", "timestamp": "2024-01-01T00:00:00Z",
         "payload": {"type": "user_message", "message": "message from unknown project"}},
    ])
    extractor = CodexExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500, project_path="")
    assert any("unknown project" in m.text for m in messages)
