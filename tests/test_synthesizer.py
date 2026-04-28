from unittest.mock import MagicMock, patch, mock_open
from mind.synthesizer import build_prompt, run_synthesis
from mind.config import Config
from pathlib import Path
import io


def _make_config(tmp_path: Path) -> Config:
    (tmp_path / "_mind").mkdir(exist_ok=True)
    (tmp_path / "_mind" / "mind.toml").write_text("""
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


def _make_popen_mock(stdout_text: str, returncode: int = 0):
    """Create a mock for subprocess.Popen context manager."""
    mock_proc = MagicMock()
    mock_proc.stdout = iter(stdout_text.splitlines(keepends=True))
    mock_proc.returncode = returncode
    mock_proc.wait.return_value = None
    mock_proc.stderr.read.return_value = "error output"
    mock_popen = MagicMock()
    mock_popen.__enter__ = MagicMock(return_value=mock_proc)
    mock_popen.__exit__ = MagicMock(return_value=False)
    return mock_popen, mock_proc


def test_run_synthesis_calls_subprocess(tmp_path):
    cfg = _make_config(tmp_path)
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir(exist_ok=True)
    mock_popen, _ = _make_popen_mock("# updated mind content\n")
    with patch("subprocess.Popen", return_value=mock_popen) as mock_cls:
        run_synthesis(cfg, "test prompt", mind_dir)
        assert mock_cls.called
        cmd = mock_cls.call_args[0][0]
        assert "claude" in cmd[0]
        assert "-p" in cmd


def test_run_synthesis_writes_output_to_mind_md(tmp_path):
    cfg = _make_config(tmp_path)
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir(exist_ok=True)
    mock_popen, _ = _make_popen_mock("# updated mind content\n")
    with patch("subprocess.Popen", return_value=mock_popen):
        run_synthesis(cfg, "test prompt", mind_dir)
    assert (mind_dir / "mind.md").read_text() == "# updated mind content\n"


def test_run_synthesis_skips_write_if_mtime_changed(tmp_path):
    """If mind.md mtime advances during synthesis (Write tool), don't overwrite it."""
    cfg = _make_config(tmp_path)
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir(exist_ok=True)
    mind_file = mind_dir / "mind.md"
    mind_file.write_text("original content\n")

    import time

    def fake_popen_ctx(*args, **kwargs):
        # Simulate Write tool updating the file during synthesis
        time.sleep(0.01)
        mind_file.write_text("written by write tool\n")
        mock_popen, _ = _make_popen_mock("# claude output\n")
        return mock_popen

    with patch("subprocess.Popen", side_effect=fake_popen_ctx):
        run_synthesis(cfg, "test prompt", mind_dir)

    # The file should retain what the Write tool wrote, not Claude's stdout
    assert mind_file.read_text() == "written by write tool\n"


def test_run_synthesis_raises_on_failure(tmp_path):
    cfg = _make_config(tmp_path)
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir(exist_ok=True)
    import pytest
    mock_popen, _ = _make_popen_mock("", returncode=1)
    with patch("subprocess.Popen", return_value=mock_popen):
        with pytest.raises(RuntimeError, match="LLM synthesis failed"):
            run_synthesis(cfg, "test prompt", mind_dir)
