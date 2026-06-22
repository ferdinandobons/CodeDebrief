from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, cast

LOCK_STALE_SECONDS = 10 * 60


def stable_id(*parts: str, length: int = 16) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return cast(dict[str, Any], json.loads(text))
    except json.JSONDecodeError as error:
        # Name the offending file: a bare "Expecting value: line 1 column 1" gives a
        # caller no way to find which cache/model file is corrupt.
        raise ValueError(f"invalid JSON in {path}: {error}") from error


def write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding=encoding,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            with suppress(OSError):
                temp_path.unlink()
        raise


def atomic_write_text_batch(
    items: Mapping[Path, str],
    *,
    encoding: str = "utf-8",
) -> None:
    """Write multiple text files with best-effort rollback on replace failures.

    Each temp file is fsynced before any destination is touched. If a later replace fails,
    previously replaced files are restored from same-directory backups where possible.
    """
    if not items:
        return

    temp_paths: dict[Path, Path] = {}
    backup_paths: dict[Path, Path | None] = {}
    replaced: list[Path] = []
    try:
        for target, text in items.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding=encoding,
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
                temp_paths[target] = Path(handle.name)

        for target in temp_paths:
            if target.exists():
                backup = _sibling_temp_path(target, ".bak")
                target.replace(backup)
                backup_paths[target] = backup
            else:
                backup_paths[target] = None

        for target, temp_path in temp_paths.items():
            temp_path.replace(target)
            replaced.append(target)
    except Exception:
        _rollback_batch_write(replaced, backup_paths)
        raise
    finally:
        for temp_path in temp_paths.values():
            with suppress(OSError):
                temp_path.unlink()
        for backup_path in backup_paths.values():
            if backup_path is not None:
                with suppress(OSError):
                    backup_path.unlink()


@contextmanager
def project_update_lock(root: Path, *, timeout: float = 30.0) -> Iterator[None]:
    lock_dir = root.resolve() / ".codedebrief"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "update.lock"
    deadline = time.monotonic() + timeout
    fd: int | None = None
    try:
        while True:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                payload = f"pid={os.getpid()}\ncreated_at={time.time()}\n"
                os.write(fd, payload.encode("utf-8"))
                os.fsync(fd)
                break
            except FileExistsError:
                _clear_stale_lock(lock_path)
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Timed out waiting for CodeDebrief update lock at {lock_path}"
                    ) from None
                time.sleep(0.1)
        yield
    finally:
        if fd is not None:
            with suppress(OSError):
                os.close(fd)
            with suppress(OSError):
                lock_path.unlink()


def _rollback_batch_write(replaced: list[Path], backup_paths: dict[Path, Path | None]) -> None:
    for target in reversed(replaced):
        backup = backup_paths.get(target)
        with suppress(OSError):
            target.unlink()
        if backup is not None and backup.exists():
            with suppress(OSError):
                backup.replace(target)
    for target, backup in backup_paths.items():
        if target in replaced:
            continue
        if backup is not None and backup.exists():
            with suppress(OSError):
                backup.replace(target)


def _sibling_temp_path(target: Path, suffix: str) -> Path:
    fd, raw_path = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=suffix,
    )
    os.close(fd)
    path = Path(raw_path)
    path.unlink()
    return path


def _clear_stale_lock(lock_path: Path) -> None:
    with suppress(OSError):
        age = time.time() - lock_path.stat().st_mtime
        if age > LOCK_STALE_SECONDS:
            lock_path.unlink()


def compact_text(value: str, limit: int = 100) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def metadata_scope_names(metadata: dict[str, Any]) -> list[str]:
    scopes = metadata.get("scope", [])
    if isinstance(scopes, str):
        return [scopes] if scopes else []
    if not isinstance(scopes, (list, tuple, set)):
        return []
    names: list[str] = []
    for scope in scopes:
        if scope is None:
            continue
        name = scope if isinstance(scope, str) else str(scope)
        if name:
            names.append(name)
    return names


def relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
