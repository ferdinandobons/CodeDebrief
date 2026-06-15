"""Stage 7 sync machinery: git auto-sync hook management."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from logicchart.hooks import hooks_status, install_hooks, uninstall_hooks


def _git_repo(tmp_path: Path) -> Path:
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    return tmp_path


def test_install_writes_executable_hooks_and_merge_driver(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    changed = install_hooks(tmp_path)

    post_commit = tmp_path / ".git" / "hooks" / "post-commit"
    assert post_commit in changed
    assert "logicchart update" in post_commit.read_text(encoding="utf-8")
    assert os.stat(post_commit).st_mode & stat.S_IXUSR
    assert "logic-flow.json merge=union" in (tmp_path / ".gitattributes").read_text(
        encoding="utf-8"
    )

    assert hooks_status(tmp_path) == {"post-commit": True, "post-checkout": True}
    # Installing again is a no-op.
    assert install_hooks(tmp_path) == []


def test_install_preserves_an_existing_hook(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    existing = tmp_path / ".git" / "hooks" / "post-commit"
    existing.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")

    install_hooks(tmp_path)
    text = existing.read_text(encoding="utf-8")
    assert "echo mine" in text
    assert "logicchart update" in text


def test_uninstall_removes_only_the_managed_block(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    install_hooks(tmp_path)
    removed = uninstall_hooks(tmp_path)

    assert any(path.name == "post-commit" for path in removed)
    assert hooks_status(tmp_path) == {"post-commit": False, "post-checkout": False}


def test_uninstall_is_symmetric_with_gitattributes(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    install_hooks(tmp_path)
    attributes = tmp_path / ".gitattributes"
    assert "logic-flow.json merge=union" in attributes.read_text(encoding="utf-8")

    removed = uninstall_hooks(tmp_path)

    assert any(path.name == ".gitattributes" for path in removed)
    assert not attributes.exists() or "logic-flow.json merge=union" not in attributes.read_text(
        encoding="utf-8"
    )


def test_uninstall_preserves_other_gitattributes(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / ".gitattributes").write_text("*.py text\n", encoding="utf-8")
    install_hooks(tmp_path)
    uninstall_hooks(tmp_path)

    text = (tmp_path / ".gitattributes").read_text(encoding="utf-8")
    assert "*.py text" in text
    assert "logic-flow.json merge=union" not in text


def test_hook_requires_a_git_repository(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        install_hooks(tmp_path)
