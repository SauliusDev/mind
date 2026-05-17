from pathlib import Path
from unittest.mock import patch
import shutil
import json as _json
from mind.sync import run_sync
from mind.config import Config
from mind.cache import FacetCache
from mind.index import Index

FIXTURES = Path(__file__).parent / "fixtures"


def _make_project(tmp_path: Path) -> tuple[Path, Config]:
    (tmp_path / "_mind").mkdir(exist_ok=True)
    (tmp_path / "_mind" / "mind.toml").write_text("""
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
    mind_dir.mkdir(exist_ok=True)
    (mind_dir / "mind.md").write_text("# mind — test-project\n## behavior\n")
    cfg = Config.load(tmp_path)
    return mind_dir, cfg


def test_sync_calls_synthesis_when_new_content(tmp_path):
    mind_dir, cfg = _make_project(tmp_path)
    transcripts = tmp_path / ".claude_projects" / "-home-ubuntu-test-project"
    transcripts.mkdir(parents=True)
    shutil.copy(FIXTURES / "claude_sample.jsonl", transcripts / "session1.jsonl")

    empty = '{"corrections": [], "workflows": [], "decisions": [], ' \
            '"friction": [], "lessons": [], "prompting_gaps": []}'
    with patch("mind.compressor._run_haiku", return_value=empty) as mh:
        with patch("mind.sync.run_synthesis") as mock_synth:
            with patch("mind.extractors.claude.ClaudeExtractor.find_project_path",
                       return_value=str(transcripts)):
                run_sync(cfg, mind_dir, project_path=str(tmp_path))
            # claude content actually flowed through the per-file pipeline ...
            assert mh.called
            # ... and that triggered synthesis:
            assert mock_synth.called


def test_sync_skips_synthesis_when_nothing_new(tmp_path):
    mind_dir, cfg = _make_project(tmp_path)
    with patch("mind.sync.run_synthesis") as mock_synth:
        run_sync(cfg, mind_dir, project_path=str(tmp_path))
        assert not mock_synth.called


def test_sync_no_message_cap(tmp_path):
    """run_sync must not truncate: with an ample cap every claude session
    file reaches the compressor and gets its own cache entry."""
    mind_dir, cfg = _make_project(tmp_path)
    cfg.max_extractions_per_sync = 50
    transcripts = tmp_path / ".claude_projects" / "-home-ubuntu-test-project"
    transcripts.mkdir(parents=True)
    sample = FIXTURES / "claude_sample.jsonl"
    for i in range(5):
        shutil.copy(sample, transcripts / f"session{i}.jsonl")

    empty = '{"corrections": [], "workflows": [], "decisions": [], ' \
            '"friction": [], "lessons": [], "prompting_gaps": []}'
    with patch("mind.compressor._run_haiku", return_value=empty) as mh:
        with patch("mind.sync.run_synthesis"):
            with patch("mind.extractors.claude.ClaudeExtractor.find_project_path",
                       return_value=str(transcripts)):
                run_sync(cfg, mind_dir, project_path=str(tmp_path))

    # All 5 session files processed (none capped/truncated away):
    cache_files = list((mind_dir / "facets" / "claude").glob("*.json"))
    assert len(cache_files) == 5
    # And each reached the compressor (Haiku invoked at least once per session):
    assert mh.call_count >= 5


def _claude_dir(tmp_path):
    d = tmp_path / ".claude_projects" / "-home-ubuntu-test-project"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session(d, name, n_user):
    lines = ['{"type":"permission-mode","permissionMode":"x","sessionId":"s"}']
    for i in range(n_user):
        lines.append(
            '{"type":"user","message":{"role":"user","content":'
            f'[{{"type":"text","text":"u{i}"}}]}},"uuid":"u{i}","timestamp":"2026-04-18T09:0{i}:00Z"}}'
        )
    (d / name).write_text("\n".join(lines) + "\n")


def test_sync_caps_extractions_and_leaves_rest_pending(tmp_path):
    mind_dir, cfg = _make_project(tmp_path)
    cfg.max_extractions_per_sync = 2
    d = _claude_dir(tmp_path)
    for i in range(5):
        _session(d, f"s{i}.jsonl", 3)
    with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=str(d)):
        with patch("mind.sync.run_synthesis"):
            with patch("mind.compressor._run_haiku") as mh:
                mh.return_value = _json.dumps({
                    "corrections": [], "workflows": [], "decisions": [],
                    "friction": [], "lessons": [], "prompting_gaps": [],
                })
                run_sync(cfg, mind_dir, project_path=str(tmp_path))
    cache_files = list((mind_dir / "facets" / "claude").glob("*.json"))
    assert len(cache_files) == 2


def test_sync_raising_cap_picks_up_pending(tmp_path):
    mind_dir, cfg = _make_project(tmp_path)
    cfg.max_extractions_per_sync = 2
    d = _claude_dir(tmp_path)
    for i in range(5):
        _session(d, f"s{i}.jsonl", 3)
    empty = _json.dumps({"corrections": [], "workflows": [], "decisions": [],
                         "friction": [], "lessons": [], "prompting_gaps": []})
    with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=str(d)):
        with patch("mind.sync.run_synthesis"):
            with patch("mind.compressor._run_haiku", return_value=empty):
                run_sync(cfg, mind_dir, project_path=str(tmp_path))
                cfg.max_extractions_per_sync = 50
                run_sync(cfg, mind_dir, project_path=str(tmp_path))
    cache_files = list((mind_dir / "facets" / "claude").glob("*.json"))
    assert len(cache_files) == 5


def test_sync_skips_synthesis_when_all_reuse_and_already_synced(tmp_path):
    mind_dir, cfg = _make_project(tmp_path)
    d = _claude_dir(tmp_path)
    for i in range(2):
        _session(d, f"s{i}.jsonl", 3)
    empty = _json.dumps({"corrections": [], "workflows": [], "decisions": [],
                         "friction": [], "lessons": [], "prompting_gaps": []})
    with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=str(d)):
        with patch("mind.compressor._run_haiku", return_value=empty):
            with patch("mind.sync.run_synthesis") as synth1:
                run_sync(cfg, mind_dir, project_path=str(tmp_path))
                assert synth1.called  # first sync synthesizes
            # second sync: no file changes -> all reuse, sync_count>0 -> skip synthesis
            with patch("mind.sync.run_synthesis") as synth2:
                run_sync(cfg, mind_dir, project_path=str(tmp_path))
                assert not synth2.called


def test_sync_synthesizes_when_sync_count_zero_even_if_all_cached(tmp_path):
    mind_dir, cfg = _make_project(tmp_path)
    d = _claude_dir(tmp_path)
    _session(d, "s0.jsonl", 3)
    empty = _json.dumps({"corrections": [], "workflows": [], "decisions": [],
                         "friction": [], "lessons": [], "prompting_gaps": []})
    with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=str(d)):
        with patch("mind.compressor._run_haiku", return_value=empty):
            with patch("mind.sync.run_synthesis"):
                run_sync(cfg, mind_dir, project_path=str(tmp_path))  # warms cache, sync_count -> 1
        # Simulate `mind rebuild`/interrupted: cache stays warm but sync_count reset to 0
        idx = Index.load(mind_dir)
        idx.sync_count = 0
        idx.write(mind_dir)
        with patch("mind.compressor._run_haiku", return_value=empty):
            with patch("mind.sync.run_synthesis") as synth:
                run_sync(cfg, mind_dir, project_path=str(tmp_path))
                # all files are cache-reuse now, but sync_count==0 -> MUST synthesize
                assert synth.called
