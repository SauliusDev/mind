from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SourceIndex:
    path: str
    files: dict[str, str] = field(default_factory=dict)  # filename → mtime ISO string


@dataclass
class Index:
    project: str
    project_path: str
    last_sync: str
    sync_count: int
    llm: str
    sources: dict[str, SourceIndex] = field(default_factory=dict)

    @classmethod
    def load(cls, mind_dir: Path) -> Index:
        path = mind_dir / "index.yaml"
        if not path.exists():
            return cls(
                project="",
                project_path="",
                last_sync="",
                sync_count=0,
                llm="claude",
            )
        data = yaml.safe_load(path.read_text()) or {}
        sources: dict[str, SourceIndex] = {}
        for tool, src in (data.get("sources") or {}).items():
            sources[tool] = SourceIndex(
                path=src.get("path", ""),
                files={str(k): str(v) for k, v in (src.get("files") or {}).items()},
            )
        return cls(
            project=data.get("project", ""),
            project_path=data.get("project_path", ""),
            last_sync=data.get("last_sync", ""),
            sync_count=int(data.get("sync_count", 0)),
            llm=data.get("llm", "claude"),
            sources=sources,
        )

    def known_files(self, tool: str) -> dict[str, str]:
        src = self.sources.get(tool)
        return dict(src.files) if src else {}

    def write(self, mind_dir: Path) -> None:
        mind_dir.mkdir(parents=True, exist_ok=True)
        data: dict = {
            "project": self.project,
            "project_path": self.project_path,
            "last_sync": self.last_sync,
            "sync_count": self.sync_count,
            "llm": self.llm,
            "sources": {
                tool: {"path": src.path, "files": src.files}
                for tool, src in self.sources.items()
            },
        }
        (mind_dir / "index.yaml").write_text(
            yaml.dump(data, default_flow_style=False)
        )
