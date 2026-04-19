from pathlib import Path
import shutil
from mind.extractors.cursor import CursorExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_extracts_user_and_assistant(tmp_path):
    transcript_dir = tmp_path / "agent-transcripts" / "sess1"
    transcript_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / "cursor_sample.jsonl", transcript_dir / "sess1.jsonl")
    extractor = CursorExtractor()
    messages, _ = extractor.extract_new(str(tmp_path / "agent-transcripts"), known_files={}, max_chars=500)
    roles = [m.role for m in messages]
    assert "user" in roles
    assert "assistant" in roles

def test_skips_unchanged(tmp_path):
    transcript_dir = tmp_path / "agent-transcripts" / "sess1"
    transcript_dir.mkdir(parents=True)
    dest = transcript_dir / "sess1.jsonl"
    shutil.copy(FIXTURES / "cursor_sample.jsonl", dest)
    from datetime import datetime, timezone
    mtime = datetime.fromtimestamp(dest.stat().st_mtime, tz=timezone.utc).isoformat()
    extractor = CursorExtractor()
    messages, _ = extractor.extract_new(
        str(tmp_path / "agent-transcripts"),
        known_files={"sess1/sess1.jsonl": mtime},
        max_chars=500,
    )
    assert messages == []

def test_find_project_path_slug(tmp_path):
    slug_dir = tmp_path / "-home-ubuntu-myproject" / "agent-transcripts"
    slug_dir.mkdir(parents=True)
    extractor = CursorExtractor(base_dir=str(tmp_path))
    result = extractor.find_project_path("/home/ubuntu/myproject")
    assert result is not None
    assert "agent-transcripts" in result
