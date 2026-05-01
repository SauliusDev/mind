from pathlib import Path
import shutil
from mind.extractors.claude import ClaudeExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_extracts_user_and_assistant_text(tmp_path):
    src = FIXTURES / "claude_sample.jsonl"
    shutil.copy(src, tmp_path / "abc123.jsonl")
    extractor = ClaudeExtractor()
    messages, updated, _, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500)
    roles = [m.role for m in messages]
    assert "user" in roles
    assert "assistant" in roles

def test_skips_tool_use_and_tool_result(tmp_path):
    src = FIXTURES / "claude_sample.jsonl"
    shutil.copy(src, tmp_path / "abc123.jsonl")
    extractor = ClaudeExtractor()
    messages, *_ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500)
    for m in messages:
        assert not m.text.startswith("<")
        assert "tool_use" not in m.text

def test_skips_slash_commands(tmp_path):
    jl = tmp_path / "sess.jsonl"
    jl.write_text('{"type":"user","message":{"role":"user","content":[{"type":"text","text":"/mind-sync"}]},"timestamp":"2026-04-18T10:00:00.000Z"}\n')
    extractor = ClaudeExtractor()
    messages, *_ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500)
    assert all(not m.text.startswith("/") for m in messages)

def test_skips_already_known_unchanged_file(tmp_path):
    src = FIXTURES / "claude_sample.jsonl"
    dest = tmp_path / "abc123.jsonl"
    shutil.copy(src, dest)
    from datetime import datetime, timezone
    mtime = datetime.fromtimestamp(dest.stat().st_mtime, tz=timezone.utc).isoformat()
    extractor = ClaudeExtractor()
    messages, *_ = extractor.extract_new(str(tmp_path), known_files={"abc123.jsonl": mtime}, max_chars=500)
    assert messages == []

def test_updated_files_contains_new_mtime(tmp_path):
    src = FIXTURES / "claude_sample.jsonl"
    shutil.copy(src, tmp_path / "abc123.jsonl")
    extractor = ClaudeExtractor()
    _, updated, *_ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500)
    assert "abc123.jsonl" in updated

def test_find_project_path_slug_decode(tmp_path):
    proj = tmp_path / "projects" / "-home-ubuntu-myproject"
    proj.mkdir(parents=True)
    extractor = ClaudeExtractor(base_dir=str(tmp_path / "projects"))
    result = extractor.find_project_path("/home/ubuntu/myproject")
    assert result is not None
    assert "myproject" in result
