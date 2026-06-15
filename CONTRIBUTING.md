# Contributing to LogicChart

LogicChart welcomes bug reports, language fixtures, framework adapters, documentation, and
code contributions.

## Development Setup

```bash
uv sync --extra dev --extra mcp
uv run pytest
```

Before submitting a pull request:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov
```

## Analyzer Changes

Every analyzer change should include a minimal source fixture and assertions for:

- detected entry points;
- decision nodes and branch labels;
- source locations;
- evidence level;
- expected findings without overstating heuristics.

Keep language-specific extraction separate from the shared logical IR. Framework knowledge
belongs in a focused adapter or classifier, not in the renderer.

## Compatibility

LogicChart supports Python 3.10 and later. Avoid changing the canonical JSON schema without
updating `schema_version`, migration notes, and serialization tests.
