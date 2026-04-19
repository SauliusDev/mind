from mind.index import Index, SourceIndex


def test_index_round_trip(tmp_path):
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()
    idx = Index(
        project="my-project",
        project_path=str(tmp_path),
        last_sync="2026-04-18T10:00:00Z",
        sync_count=5,
        llm="claude",
        sources={
            "claude": SourceIndex(
                path="/home/ubuntu/.claude/projects/foo",
                files={"abc.jsonl": "2026-04-18T09:00:00Z"},
            )
        },
    )
    idx.write(mind_dir)
    loaded = Index.load(mind_dir)
    assert loaded.project == "my-project"
    assert loaded.sync_count == 5
    assert loaded.sources["claude"].files["abc.jsonl"] == "2026-04-18T09:00:00Z"


def test_index_missing_returns_empty(tmp_path):
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()
    idx = Index.load(mind_dir)
    assert idx.project == ""
    assert idx.sync_count == 0
    assert idx.sources == {}


def test_index_known_files_for_tool(tmp_path):
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()
    idx = Index(
        project="p",
        project_path=str(tmp_path),
        last_sync="2026-04-18T10:00:00Z",
        sync_count=1,
        llm="claude",
        sources={
            "claude": SourceIndex(
                path="/foo", files={"a.jsonl": "2026-04-17T00:00:00Z"}
            )
        },
    )
    known = idx.known_files("claude")
    assert known == {"a.jsonl": "2026-04-17T00:00:00Z"}


def test_index_known_files_missing_tool(tmp_path):
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()
    idx = Index.load(mind_dir)
    assert idx.known_files("claude") == {}
