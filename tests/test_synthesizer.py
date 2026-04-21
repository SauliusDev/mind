from unittest.mock import patch, MagicMock
from mind.synthesizer import build_prompt, run_synthesis
from mind.config import Config
from pathlib import Path


def _make_config(tmp_path: Path) -> Config:
    (tmp_path / "mind.toml").write_text("""
[project]
name = "test-project"
[llm]
provider = "claude"
[tools]
enabled = ["claude"]
""")
    return Config.load(tmp_path)


SAMPLE_FACETS = {
    "corrections": ["don't use httpx"],
    "workflows": ["fetch → filter → write parquet"],
    "decisions": ["chose DuckDB"],
    "friction": ["AI kept adding unrelated code"],
    "lessons": ["✓ bulk inserts 50x faster"],
    "prompting_gaps": ["user said 'the data' without specifying which file"],
}

EMPTY_FACETS = {
    "corrections": [], "workflows": [], "decisions": [],
    "friction": [], "lessons": [], "prompting_gaps": [],
}


def test_build_prompt_contains_project_name(tmp_path):
    cfg = _make_config(tmp_path)
    prompt = build_prompt(cfg, SAMPLE_FACETS, current_mind="# mind — test-project\n")
    assert "test-project" in prompt


def test_build_prompt_includes_corrections(tmp_path):
    cfg = _make_config(tmp_path)
    prompt = build_prompt(cfg, SAMPLE_FACETS, current_mind="")
    assert "don't use httpx" in prompt


def test_build_prompt_includes_current_mind(tmp_path):
    cfg = _make_config(tmp_path)
    current = "# mind — test-project\n## behavior\n- never do X\n"
    prompt = build_prompt(cfg, EMPTY_FACETS, current_mind=current)
    assert "never do X" in prompt


def test_build_prompt_no_facets(tmp_path):
    cfg = _make_config(tmp_path)
    prompt = build_prompt(cfg, EMPTY_FACETS, current_mind="")
    assert "test-project" in prompt
    assert "(none)" in prompt


def test_run_synthesis_calls_subprocess(tmp_path):
    cfg = _make_config(tmp_path)
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        run_synthesis(cfg, "test prompt", mind_dir)
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "claude" in cmd[0]
        assert "-p" in cmd


def test_run_synthesis_raises_on_failure(tmp_path):
    cfg = _make_config(tmp_path)
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()
    import pytest
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        with pytest.raises(RuntimeError, match="LLM synthesis failed"):
            run_synthesis(cfg, "test prompt", mind_dir)
