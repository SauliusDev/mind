import sys
import pytest
from mind.config import Config, resolve_tool_path


def test_config_defaults(tmp_path):
    (tmp_path / "_mind").mkdir(exist_ok=True)
    toml = tmp_path / "_mind" / "mind.toml"
    toml.write_text("""
[project]
name = "my-project"
[llm]
provider = "claude"
[tools]
enabled = ["claude", "gemini"]
""")
    cfg = Config.load(tmp_path)
    assert cfg.project_name == "my-project"
    assert cfg.llm_provider == "claude"
    assert cfg.enabled_tools == ["claude", "gemini"]
    assert cfg.max_message_chars == 0
    assert cfg.mind_max_lines == 150


def test_config_new_fields(tmp_path):
    (tmp_path / "_mind").mkdir(exist_ok=True)
    toml = tmp_path / "_mind" / "mind.toml"
    toml.write_text("""
[project]
name = "my-project"
[llm]
provider = "claude"
haiku_command = "myhaiku -p {prompt}"
[limits]
chunk_size = 50
[tools]
enabled = ["claude"]
""")
    cfg = Config.load(tmp_path)
    assert cfg.haiku_command == "myhaiku -p {prompt}"
    assert cfg.chunk_size == 50


def test_config_defaults_new_fields(tmp_path):
    (tmp_path / "_mind").mkdir(exist_ok=True)
    toml = tmp_path / "_mind" / "mind.toml"
    toml.write_text("""
[project]
name = "my-project"
[llm]
provider = "claude"
[tools]
enabled = ["claude"]
""")
    cfg = Config.load(tmp_path)
    assert cfg.haiku_command == "claude -p {prompt} --model claude-haiku-4-5-20251001"
    assert cfg.chunk_size == 30


def test_config_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        Config.load(tmp_path)


def test_resolve_tool_path_simple():
    path = resolve_tool_path("claude")
    assert "claude" in path.lower()


def test_resolve_tool_path_copilot_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    path = resolve_tool_path("copilot")
    assert "Code" in path


def test_resolve_tool_path_copilot_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    path = resolve_tool_path("copilot")
    assert "Application Support" in path


def test_new_limit_defaults(tmp_path):
    (tmp_path / "_mind").mkdir()
    (tmp_path / "_mind" / "mind.toml").write_text(
        '[project]\nname = "p"\n[llm]\nprovider = "claude"\n[tools]\nenabled = ["claude"]\n'
    )
    from mind.config import Config
    cfg = Config.load(tmp_path)
    assert cfg.extraction_concurrency == 50
    assert cfg.max_extractions_per_sync == 50
    assert cfg.min_user_messages == 2


def test_lookbehind_aliases_into_max_extractions(tmp_path):
    (tmp_path / "_mind").mkdir()
    (tmp_path / "_mind" / "mind.toml").write_text(
        '[project]\nname = "p"\n[llm]\nprovider = "claude"\n[tools]\nenabled = ["claude"]\n'
        '[limits]\nmax_conversations_lookbehind = 7\n'
    )
    from mind.config import Config
    cfg = Config.load(tmp_path)
    assert cfg.max_extractions_per_sync == 7


def test_explicit_max_extractions_wins_over_lookbehind(tmp_path):
    (tmp_path / "_mind").mkdir()
    (tmp_path / "_mind" / "mind.toml").write_text(
        '[project]\nname = "p"\n[llm]\nprovider = "claude"\n[tools]\nenabled = ["claude"]\n'
        '[limits]\nmax_conversations_lookbehind = 7\nmax_extractions_per_sync = 25\n'
    )
    from mind.config import Config
    cfg = Config.load(tmp_path)
    assert cfg.max_extractions_per_sync == 25
