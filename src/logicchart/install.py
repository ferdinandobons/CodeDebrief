from __future__ import annotations

from pathlib import Path

START = "<!-- logicchart:instructions:start -->"
END = "<!-- logicchart:instructions:end -->"

INSTRUCTION_BLOCK = f"""{START}
## LogicChart

This project uses LogicChart to keep decision flows synchronized with the source code.

For codebase questions about behavior, decisions, missing cases, or change impact:

1. Prefer `logicchart query "<question>"` before broad file-by-file searches.
2. Use `logicchart impact [changed files...]` before implementing a substantial change.
3. Review `logicchart-out/logic-flow.md` and any related `POTENTIAL_GAP` findings.

After a substantial code change:

1. Run `logicchart impact`.
2. Review every affected entry point and caller flow.
3. Run `logicchart update`.
4. Commit synchronized changes to:
   - `logicchart-out/logic-flow.json`
   - `logicchart-out/logic-flow.md`

Do not present inferred findings as confirmed bugs. LogicChart marks syntax-backed facts as
`VERIFIED`, deterministic heuristics as `INFERRED`, and review candidates as `POTENTIAL_GAP`.
{END}
"""


def install_agent_instructions(root: Path, platform: str = "all") -> list[Path]:
    targets: list[Path] = []
    if platform in {"all", "codex"}:
        targets.append(root / "AGENTS.md")
    if platform in {"all", "claude"}:
        targets.append(root / "CLAUDE.md")
    if platform in {"all", "gemini"}:
        targets.append(root / "GEMINI.md")
    if platform in {"all", "cursor"}:
        targets.append(root / ".cursor" / "rules" / "logicchart.mdc")

    changed: list[Path] = []
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        updated = _upsert(existing, INSTRUCTION_BLOCK)
        if target.suffix == ".mdc" and not updated.startswith("---"):
            frontmatter = (
                "---\ndescription: Keep LogicChart synchronized\nalwaysApply: true\n---\n\n"
            )
            updated = frontmatter + updated
        if updated != existing:
            target.write_text(updated, encoding="utf-8")
            changed.append(target)
    return changed


def _upsert(existing: str, block: str) -> str:
    if START in existing and END in existing:
        before, remainder = existing.split(START, 1)
        _, after = remainder.split(END, 1)
        # When the block sits at the very top (no prose before it), don't reintroduce a
        # leading blank line - otherwise re-running `install` on a freshly created file
        # would keep prepending whitespace instead of reaching a fixed point.
        prefix = before.rstrip() + "\n\n" if before.strip() else ""
        return prefix + block.rstrip() + "\n" + after.lstrip()
    if not existing.strip():
        # Match the fixed point the upsert branch produces for a block-only file, so a
        # second `install` on a freshly created file is a true no-op.
        return block.rstrip() + "\n"
    return existing.rstrip() + "\n\n" + block.rstrip() + "\n"
