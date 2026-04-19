from pathlib import Path
import shutil
from mind.extractors.gemini import GeminiExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_extracts_user_and_gemini_messages(tmp_path):
    shutil.copy(FIXTURES / "gemini_sample.json", tmp_path / "session-2026-04-18T10-15-ddac3d5b.json")
    extractor = GeminiExtractor()
    messages, updated = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500)
    roles = [m.role for m in messages]
    assert "user" in roles
    assert "assistant" in roles

def test_skips_error_messages(tmp_path):
    shutil.copy(FIXTURES / "gemini_sample.json", tmp_path / "session-abc.json")
    extractor = GeminiExtractor()
    messages, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500)
    assert all(m.role != "error" for m in messages)

def test_skips_unchanged_file(tmp_path):
    dest = tmp_path / "session-abc.json"
    shutil.copy(FIXTURES / "gemini_sample.json", dest)
    from datetime import datetime, timezone
    mtime = datetime.fromtimestamp(dest.stat().st_mtime, tz=timezone.utc).isoformat()
    extractor = GeminiExtractor()
    messages, _ = extractor.extract_new(str(tmp_path), known_files={"session-abc.json": mtime}, max_chars=500)
    assert messages == []

def test_find_project_path_by_dirname(tmp_path):
    proj = tmp_path / "cvt-scanner" / "chats"
    proj.mkdir(parents=True)
    extractor = GeminiExtractor(base_dir=str(tmp_path))
    result = extractor.find_project_path("/home/ubuntu/cvt-scanner")
    assert result is not None
    assert "chats" in result
