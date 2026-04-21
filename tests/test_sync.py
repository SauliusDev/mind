from pathlib import Path
from unittest.mock import patch
import shutil
from mind.sync import run_sync
from mind.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


def _make_project(tmp_path: Path) -> tuple[Path, Config]:
    (tmp_path / "mind.toml").write_text("""
[project]
name = "test-project"
[llm]
provider = "claude"
[tools]
enabled = ["claude"]
[limits]
chunk_size = 10
""")
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()
    (mind_dir / "mind.md").write_text("# mind — test-project\n## behavior\n")
    cfg = Config.load(tmp_path)
    return mind_dir, cfg


def test_sync_calls_synthesis_when_new_content(tmp_path):
    mind_dir, cfg = _make_project(tmp_path)
    transcripts = tmp_path / ".claude_projects" / "-home-ubuntu-test-project"
    transcripts.mkdir(parents=True)
    shutil.copy(FIXTURES / "claude_sample.jsonl", transcripts / "session1.jsonl")

    with patch("mind.sync.load_or_extract") as mock_compress:
        mock_compress.return_value = {
            "corrections": [], "workflows": [], "decisions": [],
            "friction": [], "lessons": [], "prompting_gaps": [],
        }
        with patch("mind.sync.run_synthesis") as mock_synth:
            with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=str(transcripts)):
                run_sync(cfg, mind_dir, project_path=str(tmp_path))
            assert mock_synth.called


def test_sync_skips_synthesis_when_nothing_new(tmp_path):
    mind_dir, cfg = _make_project(tmp_path)
    with patch("mind.sync.run_synthesis") as mock_synth:
        run_sync(cfg, mind_dir, project_path=str(tmp_path))
        assert not mock_synth.called


def test_sync_no_message_cap(tmp_path):
    """run_sync must not truncate messages — all new files go to compressor."""
    mind_dir, cfg = _make_project(tmp_path)
    transcripts = tmp_path / ".claude_projects" / "-home-ubuntu-test-project"
    transcripts.mkdir(parents=True)

    # Write 5 separate session files
    sample = FIXTURES / "claude_sample.jsonl"
    for i in range(5):
        shutil.copy(sample, transcripts / f"session{i}.jsonl")

    captured_messages = []

    def capture(project_path, tool, files, messages, cfg, cache_dir):
        captured_messages.extend(messages)
        return {"corrections": [], "workflows": [], "decisions": [],
                "friction": [], "lessons": [], "prompting_gaps": []}

    with patch("mind.sync.load_or_extract", side_effect=capture):
        with patch("mind.sync.run_synthesis"):
            with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=str(transcripts)):
                run_sync(cfg, mind_dir, project_path=str(tmp_path))

    # All messages from all files must reach the compressor (no cap)
    assert len(captured_messages) > 0
