# safaribooks



## Stack

- **Language:** Python (uv for dependency management)
- **Style:** async-first, Pydantic v2 for models, type-annotated throughout

## Commands

```sh
uv run pytest          # run tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run mypy .          # type check
```

## Conventions

- Tests live in `tests/`, mirroring `src/` structure
- Use `uv add` to add dependencies, never edit `pyproject.toml` by hand for deps
- Prefer `pathlib.Path` over `os.path`
- Async by default; only use sync where the library forces it

## Agent Instruction Files

`AGENTS.md` (this file) is the source of truth — readable by Codex, Gemini, OpenCode, Cursor, and GitHub Copilot directly.
`CLAUDE.md` contains only `@AGENTS.md` so Claude Code imports this file inline.

Do **not** write `@filename` imports in AGENTS.md — that syntax is Claude Code-only and does nothing in other tools.
