"""Self-exclusion of CodeDebrief's own source from discovery (Stage 0).

These pin both directions: the tool's own package/tests are dropped when analyzing
its source checkout, and a *user* project that merely happens to have a
``src/codedebrief`` or ``tests`` directory keeps all of its files.
"""

from __future__ import annotations

from pathlib import Path

from codedebrief.analysis.discovery import (
    _SELF_PACKAGE_DIR,
    _self_exclude_roots,
    discover_source_files,
)
from codedebrief.config import CodeDebriefConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_self_exclude_roots_in_checkout() -> None:
    roots = _self_exclude_roots(PROJECT_ROOT)
    assert _SELF_PACKAGE_DIR in roots
    assert (PROJECT_ROOT / "tests").resolve() in roots


def test_self_exclude_roots_for_arbitrary_project(tmp_path: Path) -> None:
    # Only the running package is excluded; a user's own tests/ is never dropped.
    assert _self_exclude_roots(tmp_path) == [_SELF_PACKAGE_DIR]


def test_self_exclude_drops_own_package_in_checkout() -> None:
    with_exclude = discover_source_files(
        PROJECT_ROOT, CodeDebriefConfig(source_roots=["src"], self_exclude=True)
    )
    without_exclude = discover_source_files(
        PROJECT_ROOT, CodeDebriefConfig(source_roots=["src"], self_exclude=False)
    )

    # `src/` is entirely CodeDebrief's own package, so self-exclude empties it.
    assert with_exclude == []
    assert any(p.resolve().is_relative_to(_SELF_PACKAGE_DIR) for p in without_exclude)


def test_self_exclude_keeps_user_files_named_like_codedebrief(tmp_path: Path) -> None:
    package = tmp_path / "src" / "codedebrief"
    package.mkdir(parents=True)
    (package / "thing.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_thing.py").write_text("def test_f():\n    assert True\n", encoding="utf-8")

    discovered = {
        p.name
        for p in discover_source_files(
            tmp_path, CodeDebriefConfig(source_roots=["src", "tests"], self_exclude=True)
        )
    }

    # A coincidental src/codedebrief in a user project is not the running package.
    assert {"thing.py", "test_thing.py"} <= discovered
