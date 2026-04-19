from pathlib import Path
from mind.extractors.codex import CodexExtractor


def _make_history(tmp_path: Path, entries: list[dict]) -> Path:
    import json
    jl = tmp_path / "history.jsonl"
    lines = [json.dumps(e) for e in entries]
    jl.write_text("\n".join(lines) + "\n")
    return jl


def test_extracts_from_history_jsonl(tmp_path):
    _make_history(tmp_path, [
        {"session_id": "s1", "ts": 1776000000, "text": "fix the validator timeout"},
        {"session_id": "s1", "ts": 1776000010, "text": "here is the fix I applied"},
    ])
    extractor = CodexExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500)
    assert len(messages) >= 1
    assert any("validator" in m.text for m in messages)

def test_skips_unchanged_history(tmp_path):
    _make_history(tmp_path, [{"session_id": "s1", "ts": 1776000000, "text": "hello"}])
    from datetime import datetime, timezone
    mtime = datetime.fromtimestamp((tmp_path / "history.jsonl").stat().st_mtime, tz=timezone.utc).isoformat()
    extractor = CodexExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={"history.jsonl": mtime}, max_chars=500)
    assert messages == []
