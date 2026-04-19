# mind

Persistent AI context management for multi-tool development.

Reads conversation transcripts from Claude Code, Gemini, Cursor, Codex, and Copilot
after every git commit. Synthesizes them into `_mind/mind.md` — a token-efficient
LLM-tuning file injected into every future session.

## Install

```bash
pip install project-mind
```

## Setup (per project)

```bash
cd your-project
mind init
```

This creates `_mind/`, installs a git hook, and writes `mind.toml`.

## Usage

```bash
mind sync      # run manually (hook calls this automatically after commits)
mind evolve    # full re-synthesis from all transcripts
mind status    # show tracked tools and last sync time
```

## Supported Tools

| Tool | Transcript location |
|---|---|
| Claude Code | `~/.claude/projects/{slug}/*.jsonl` |
| Gemini | `~/.gemini/tmp/{project}/chats/*.json` |
| Cursor | `~/.cursor/projects/{slug}/agent-transcripts/` |
| Codex | `~/.codex/history.jsonl` |
| Copilot | VS Code `workspaceStorage/{hash}/state.vscdb` |

## Configuration (`mind.toml`)

```toml
[project]
name = "my-project"

[llm]
provider = "claude"   # claude | gemini | codex

[tools]
enabled = ["claude", "gemini", "cursor", "codex", "copilot"]

[limits]
max_messages_per_sync = 150
mind_max_lines = 150
```

## How it works

1. After every `git commit`, the hook runs `mind sync` in the background
2. `mind sync` scans transcript directories for files newer than last sync
3. Extracts user + assistant text (skips tool calls, thinking blocks)
4. Calls `claude -p` (or configured LLM) with extracted content + current `mind.md`
5. LLM rewrites `mind.md` in place — compressing old entries, adding new ones

## `mind.md` format

```markdown
## behavior     ← user corrections — never compressed
## context      ← project state — rewritten each sync
## active       ← in-flight tasks
## decisions    ← architectural choices
## lessons      ← what worked / failed
## history      ← compressed timeline
```
