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


def test_find_project_path_slug_handles_underscores_and_dots(tmp_path):
    # Claude Code maps "_" and "." to "-" in the project dir name.
    proj = tmp_path / "projects" / "-home-ubuntu-etsy-bot-crafted-by-cloth-v1-0"
    proj.mkdir(parents=True)
    extractor = ClaudeExtractor(base_dir=str(tmp_path / "projects"))
    result = extractor.find_project_path("/home/ubuntu/etsy_bot/crafted_by_cloth/v1.0")
    assert result is not None
    assert result.endswith("-home-ubuntu-etsy-bot-crafted-by-cloth-v1-0")


def _write_jsonl(path, n_user):
    lines = ['{"type":"permission-mode","permissionMode":"x","sessionId":"s"}']
    for i in range(n_user):
        lines.append(
            '{"type":"user","message":{"role":"user","content":'
            f'[{{"type":"text","text":"u{i}"}}]}},"uuid":"u{i}","timestamp":"2026-04-18T09:0{i}:00Z"}}'
        )
    path.write_text("\n".join(lines) + "\n")
    return len(lines)


def test_extract_delta_full_when_from_line_zero(tmp_path):
    f = tmp_path / "s.jsonl"
    total = _write_jsonl(f, 3)
    extractor = ClaudeExtractor()
    msgs, new_lines, fp, rewritten = extractor.extract_delta(str(f), 0, "", 0)
    assert [m.text for m in msgs] == ["u0", "u1", "u2"]
    assert new_lines == total
    assert fp != "" and rewritten is False


def test_extract_delta_returns_only_new_lines(tmp_path):
    f = tmp_path / "s.jsonl"
    _write_jsonl(f, 2)
    extractor = ClaudeExtractor()
    _, line_count, fp1, _ = extractor.extract_delta(str(f), 0, "", 0)
    with open(f, "a") as fh:
        fh.write('{"type":"user","message":{"role":"user","content":'
                 '[{"type":"text","text":"u2"}]},"uuid":"u2","timestamp":"2026-04-18T09:09:00Z"}\n')
    msgs, new_count, fp2, rewritten = extractor.extract_delta(str(f), line_count, fp1, 0)
    assert [m.text for m in msgs] == ["u2"]
    assert new_count == line_count + 1
    assert rewritten is False
    assert fp2 != fp1


def test_extract_delta_detects_rewrite_on_shrink(tmp_path):
    f = tmp_path / "s.jsonl"
    _write_jsonl(f, 4)
    extractor = ClaudeExtractor()
    _, line_count, fp1, _ = extractor.extract_delta(str(f), 0, "", 0)
    _write_jsonl(f, 1)
    msgs, _, _, rewritten = extractor.extract_delta(str(f), line_count, fp1, 0)
    assert rewritten is True
    assert [m.text for m in msgs] == ["u0"]


def test_extract_delta_detects_rewrite_on_fingerprint_mismatch(tmp_path):
    f = tmp_path / "s.jsonl"
    _write_jsonl(f, 3)
    extractor = ClaudeExtractor()
    _, line_count, _, _ = extractor.extract_delta(str(f), 0, "", 0)
    msgs, _, _, rewritten = extractor.extract_delta(str(f), line_count, "wrongfingerprint0", 0)
    assert rewritten is True
