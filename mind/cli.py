from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

import click

from mind.config import Config
from mind.hook import install_hook
from mind.index import Index, SourceIndex
from mind.sync import run_sync


_MIND_MD_TEMPLATE = """\
# mind — {project_name}
_synced: {date} | sessions: 0 | tools: {llm}_

## behavior
Rules extracted from user corrections. Never compressed. Highest priority.

## context
Project just initialized. No session history yet.

## active
(none yet)

## decisions
(none yet)

## lessons
(none yet)

## history
{date}: mind initialized.
"""

_TOML_TEMPLATE = """\
[project]
name = "{project_name}"

[llm]
provider = "{llm}"

[tools]
enabled = ["claude", "gemini", "cursor", "codex", "copilot"]

[limits]
max_messages_per_sync = 150
max_message_chars = 500
mind_max_lines = 150
"""


@click.group()
def main() -> None:
    """mind — persistent AI context management."""


@main.command()
@click.option("--project-path", default=".", show_default=True)
@click.option("--name", prompt="Project name")
@click.option("--llm", default="claude", show_default=True, help="LLM provider: claude|gemini|codex")
def init(project_path: str, name: str, llm: str) -> None:
    """Initialize mind in a project."""
    root = Path(project_path).resolve()
    mind_dir = root / "_mind"
    mind_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    mind_md = mind_dir / "mind.md"
    if not mind_md.exists():
        mind_md.write_text(_MIND_MD_TEMPLATE.format(project_name=name, date=today, llm=llm))

    index = Index(
        project=name,
        project_path=str(root),
        last_sync=datetime.now(tz=timezone.utc).isoformat(),
        sync_count=0,
        llm=llm,
        sources={},
    )
    index.write(mind_dir)

    toml_path = root / "mind.toml"
    if not toml_path.exists():
        toml_path.write_text(_TOML_TEMPLATE.format(project_name=name, llm=llm))

    install_hook(root)
    click.echo(f"✓ mind initialized in {root}")
    click.echo("  _mind/mind.md     created")
    click.echo("  _mind/index.yaml  created")
    click.echo("  mind.toml         created")
    click.echo("  .git/hooks/post-commit  installed")


@main.command()
@click.option("--project-path", default=".", show_default=True)
def sync(project_path: str) -> None:
    """Extract new transcripts and update mind.md."""
    root = Path(project_path).resolve()
    cfg = Config.load(root)
    mind_dir = root / "_mind"
    run_sync(cfg, mind_dir, str(root))


@main.command()
@click.option("--project-path", default=".", show_default=True)
def evolve(project_path: str) -> None:
    """Full re-synthesis: clear index and reprocess all transcripts."""
    root = Path(project_path).resolve()
    cfg = Config.load(root)
    mind_dir = root / "_mind"

    index = Index.load(mind_dir)
    cleared = Index(
        project=index.project,
        project_path=index.project_path,
        last_sync="2000-01-01T00:00:00+00:00",
        sync_count=index.sync_count,
        llm=index.llm,
        sources={tool: SourceIndex(path=src.path, files={}) for tool, src in index.sources.items()},
    )
    cleared.write(mind_dir)
    run_sync(cfg, mind_dir, str(root))


@main.command()
@click.option("--project-path", default=".", show_default=True)
def status(project_path: str) -> None:
    """Show sync status and tracked tools."""
    root = Path(project_path).resolve()
    try:
        cfg = Config.load(root)
    except FileNotFoundError:
        click.echo("✗ mind.toml not found. Run: mind init")
        return

    index = Index.load(root / "_mind")
    click.echo(f"project:    {cfg.project_name}")
    click.echo(f"last sync:  {index.last_sync or 'never'}")
    click.echo(f"sync count: {index.sync_count}")
    click.echo(f"llm:        {cfg.llm_provider}")
    click.echo("tools:")
    for tool in cfg.enabled_tools:
        count = len(index.known_files(tool))
        click.echo(f"  {tool:<10} {count} files tracked")
