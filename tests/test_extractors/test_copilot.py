import sqlite3
import json
from pathlib import Path
from mind.extractors.copilot import CopilotExtractor


def _make_workspace_db(ws_dir: Path, project_path: str, messages: list[dict]) -> None:
    ws_dir.mkdir(parents=True)
    db = ws_dir / "state.vscdb"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
    conn.execute("INSERT INTO ItemTable VALUES (?,?)", ("folder", json.dumps({"folderUri": f"file://{project_path}"})))
    conn.execute("INSERT INTO ItemTable VALUES (?,?)", ("copilot.chatSessions", json.dumps(messages)))
    conn.commit()
    conn.close()


def test_extracts_copilot_messages(tmp_path):
    ws = tmp_path / "workspace-abc123"
    _make_workspace_db(ws, "/home/ubuntu/cvt-scanner", [
        {"role": "user", "content": "explain the egress guard"},
        {"role": "assistant", "content": "The egress guard is..."},
    ])
    extractor = CopilotExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500, project_path="/home/ubuntu/cvt-scanner")
    assert any(m.role == "user" for m in messages)
    assert any(m.role == "assistant" for m in messages)

def test_ignores_workspace_for_different_project(tmp_path):
    ws = tmp_path / "workspace-xyz"
    _make_workspace_db(ws, "/home/ubuntu/other-project", [
        {"role": "user", "content": "hello from other project"},
    ])
    extractor = CopilotExtractor(base_dir=str(tmp_path))
    messages, _ = extractor.extract_new(str(tmp_path), known_files={}, max_chars=500, project_path="/home/ubuntu/cvt-scanner")
    assert messages == []
