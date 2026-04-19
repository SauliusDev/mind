from unittest.mock import patch, MagicMock
from mind.synthesizer import build_prompt, run_synthesis
from mind.extractors.base import Message
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


def test_build_prompt_contains_project_name(tmp_path):
    cfg = _make_config(tmp_path)
    messages = [Message("user", "don't use httpx", "2026-04-18T10:00:00Z", "claude")]
    prompt = build_prompt(cfg, messages, current_mind="# mind — test-project\n")
    assert "test-project" in prompt
    assert "don't use httpx" in prompt
    assert "[USER]" in prompt

def test_build_prompt_includes_current_mind(tmp_path):
    cfg = _make_config(tmp_path)
    current = "# mind — test-project\n## behavior\n- never do X\n"
    prompt = build_prompt(cfg, [], current_mind=current)
    assert "never do X" in prompt

def test_build_prompt_no_messages(tmp_path):
    cfg = _make_config(tmp_path)
    prompt = build_prompt(cfg, [], current_mind="")
    assert "no new conversation" in prompt

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
