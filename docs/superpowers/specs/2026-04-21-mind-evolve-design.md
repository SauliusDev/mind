# mind evolve — Design Spec

**Date:** 2026-04-21  
**Version target:** 0.1.7  
**Commands affected:** `sync`, `rebuild`, `evolve` (new)

---

## Problem

The current `sync` pipeline caps messages at 150, which means long gaps between commits silently drop conversation history. Lessons, decisions, and corrections made across many sessions are never captured. This is unacceptable for a tool whose entire value is persistent memory.

---

## Solution

Replace the raw-message pipeline with a two-pass architecture:

1. **Pass 1 (Haiku)** — compress each transcript file into compact JSON facets. Cached per-file by `hash(project_path + source_path + mtime)`. Re-runs only when a file changes.
2. **Pass 2 (main LLM)** — synthesise aggregated facets into output. Output differs per command.

No message cap. All history is processed on first run; subsequent runs only pay for new/changed files.

---

## Project Scoping

All state lives inside the project's `_mind/` directory:

- Facet cache: `_mind/facets/{hash}.json`
- Evolve report: `_mind/evolve-report.md`

Transcript collection is already project-scoped via each extractor's `find_project_path()` (e.g. Claude maps project path to slug, reads only that project's JSONL files). Hash keys include `project_path` to prevent collisions.

---

## Architecture

```
All transcript files (all providers, project-scoped)
        |
        v
+-----------------------------+
|  Pass 1: Facet Extraction   |  Haiku, per-file
|  messages -> JSON facets    |  cached in _mind/facets/
|  skipped if mtime unchanged |
+-----------------------------+
        |
        v
  Aggregated facets
        |
        v
+-----------------------------+
|  Pass 2: Synthesis          |  main LLM (per cfg.llm_provider)
|  sync/rebuild -> mind.md    |
|  evolve -> evolve-report.md |
+-----------------------------+
```

---

## Facet Schema

Haiku outputs one JSON object per chunk (default 30 messages). All fields are string arrays, all optional:

```json
{
  "corrections": ["user had to re-ask X", "AI kept doing Y despite correction"],
  "workflows":   ["fetch -> filter -> write parquet (repeated)"],
  "decisions":   ["chose DuckDB over SQLite for analytical queries"],
  "friction":    ["misunderstood request", "excessive changes", "wrong approach"],
  "lessons":     ["always check mtime before reading large parquet"],
  "prompting_gaps": ["user asked vaguely about 'the data' — unclear which dataset"]
}
```

`aggregate_facets()` merges all per-file facets by concatenating each array, deduplicating by semantic similarity (simple: exact string dedup in first pass, LLM dedup in synthesis prompt).

---

## Commands

### `mind sync` (modified)

1. Collect all transcript files from all enabled providers (project-scoped)
2. For each file: `load_or_extract(file, messages, cfg, cache_dir)` — load cached facets or run Haiku
3. `aggregate_facets(all_facets)`
4. `run_synthesis(cfg, build_prompt(cfg, facets, current_mind), mind_dir)` → updated `mind.md`

Removes `max_messages_per_sync` cap. Adds `chunk_size` (default 30).

### `mind rebuild` (modified)

1. Wipe `_mind/` (existing behaviour) — including `_mind/facets/`
2. Run full sync pipeline from scratch

### `mind evolve` (new)

```
mind evolve [--project-path .] [--write]
```

1. `load_or_extract()` for all files (reuses facet cache from last sync if fresh)
2. `aggregate_facets()`
3. `build_evolve_prompt(cfg, facets, existing_claude_dir)` — passes current `.claude/` contents so LLM avoids duplicating existing rules/skills
4. `run_synthesis()` → 4-section markdown report
5. Print report to stdout
6. Save to `_mind/evolve-report.md`
7. If `--write`: materialise rules and skills as actual files in `.claude/rules/` and `.claude/skills/`; append CLAUDE.md additions

---

## Evolve Report Structure

```markdown
## Rules
Candidate .claude/rules/ files.
Each entry: suggested filename, full content, rationale (which correction pattern triggered it).

## Skills
Candidate .claude/skills/ files.
Each entry: suggested filename, trigger condition, full content.

## CLAUDE.md Additions
Project context the user repeatedly re-explained.
Ready-to-paste markdown sections.

## Prompting Techniques
Specific friction points where clearer prompting would have helped.
Concrete rewrites: "instead of X, try Y".
Always report-only — never auto-written.
```

---

## New & Modified Files

| File | Change |
|---|---|
| `mind/compressor.py` | New — `extract_facets()`, `load_or_extract()`, `aggregate_facets()` |
| `mind/evolve.py` | New — `build_evolve_prompt()`, `run_evolve()` |
| `mind/config.py` | Add `haiku_command`, `chunk_size`; remove `max_messages_per_sync` cap |
| `mind/sync.py` | Replace raw message loop with compressor pipeline |
| `mind/synthesizer.py` | `build_prompt()` accepts facets dict instead of raw messages |
| `mind/cli.py` | Add `evolve` command; `rebuild` wipes `_mind/facets/` |
| `pyproject.toml` | Bump version `0.1.6 -> 0.1.7` |

---

## Config Changes (mind.toml)

```toml
[llm]
provider = "claude"
haiku_command = "claude -p {prompt} --model claude-haiku-4-5-20251001"
chunk_size = 30
```

`haiku_command` defaults to Claude Haiku 4.5. If the user's provider is not Claude, `haiku_command` can be overridden to any fast/cheap model that accepts `-p {prompt}`.

---

## Testing

- `test_compressor.py` — unit tests for `extract_facets`, cache hit/miss, `aggregate_facets`
- `test_evolve.py` — unit tests for `build_evolve_prompt`, `run_evolve` (mock LLM)
- Existing `test_sync.py` — update to assert no message cap, uses mock compressor
- All existing tests must continue to pass

---

## Out of Scope

- Streaming/progressive output during Haiku pass
- Per-section `--only rules` flag (can be added in 0.1.8)
- HTML report format (markdown is sufficient for now)
