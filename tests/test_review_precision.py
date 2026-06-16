"""Detector/metadata precision fixes from the whole-project review."""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.common import decision_metadata
from logicchart.analysis.cross_flow import _outcomes_compatible, _raise_signature
from logicchart.analysis.project import ProjectAnalyzer
from logicchart.model import ProjectModel

_ENUM = (
    "from enum import Enum\n\n\n"
    "class Status(Enum):\n"
    "    A = 'a'\n"
    "    B = 'b'\n"
    "    C = 'c'\n"
    "    D = 'd'\n\n\n"
)


def _kinds(model: ProjectModel, flow_name: str) -> set[str]:
    flow = next(f for f in model.flows if f.name == flow_name)
    return {f.kind for f in model.findings if f.flow_id == flow.id}


# --- decision_metadata value extraction (#5) --------------------------------


def test_set_literal_values_are_extracted() -> None:
    meta = decision_metadata("status in {Status.A, Status.B}")
    assert set(meta["values"]) == {"Status.A", "Status.B"}
    assert meta["value_namespace"] == "Status"


def test_is_not_none_does_not_capture_bogus_value() -> None:
    meta = decision_metadata("user is not None")
    assert meta["operator"] == "is not"
    assert "not" not in meta["values"]
    assert meta["values"] == ["None"]


def test_set_membership_predicate_does_not_fire_enum_exhaustiveness(tmp_path: Path) -> None:
    # A single membership predicate (`if status in {A, B, C}: return 1\n return 0`) is ONE
    # case whose complement (status not in the set) is handled by the reachable `return 0`
    # fall-through - not a multi-case dispatch. It must NOT be flagged for the omitted D.
    body = (
        "def handle(status):\n"
        "    if status in {Status.A, Status.B, Status.C}:\n"
        "        return 1\n"
        "    return 0\n"
    )
    (tmp_path / "mod.py").write_text(_ENUM + body, encoding="utf-8")
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    assert "enum_exhaustiveness" not in _kinds(model, "handle")


# --- outcome_inconsistency symbolic vs literal HTTP status (#6) --------------


def test_raise_signature_normalizes_symbolic_status() -> None:
    assert _raise_signature("Raise HTTPException(status_code=403, detail='x')") == (
        "raise:HTTPException:403"
    )
    assert _raise_signature("Raise HTTPException(status.HTTP_403_FORBIDDEN)") == (
        "raise:HTTPException:403"
    )


def test_outcomes_compatible_treats_codeless_as_match() -> None:
    assert _outcomes_compatible("raise:HTTPException", "raise:HTTPException:403")
    assert _outcomes_compatible("raise:HTTPException:403", "raise:HTTPException:403")
    assert not _outcomes_compatible("raise:HTTPException:404", "raise:HTTPException:403")
    assert not _outcomes_compatible("return", "raise:HTTPException:403")


def _http_siblings(third_raise: str) -> str:
    return (
        "def check_a(u):\n"
        "    if u.role == 'guest':\n"
        "        raise HTTPException(status_code=403, detail='x')\n"
        "    return u\n\n\n"
        "def check_b(u):\n"
        "    if u.role == 'guest':\n"
        "        raise HTTPException(status_code=403, detail='y')\n"
        "    return u\n\n\n"
        "def check_c(u):\n"
        "    if u.role == 'guest':\n"
        f"        {third_raise}\n"
        "    return u\n"
    )


def test_symbolic_status_does_not_false_positive(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        _http_siblings("raise HTTPException(status.HTTP_403_FORBIDDEN)"), encoding="utf-8"
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    assert not any(f.kind == "outcome_inconsistency" for f in model.findings)


def test_genuine_status_divergence_still_fires(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        _http_siblings("raise HTTPException(status_code=404, detail='z')"), encoding="utf-8"
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    assert "outcome_inconsistency" in _kinds(model, "check_c")


# --- dead_guard local rebind / shadow (#7) ----------------------------------


def test_dead_guard_skips_locally_reassigned_constant(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "VERBOSE = True\n\n\n"
        "def run(args):\n"
        "    VERBOSE = '-v' in args\n"
        "    if VERBOSE:\n"
        "        return 1\n"
        "    return 0\n",
        encoding="utf-8",
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    assert "dead_guard" not in _kinds(model, "run")


def test_dead_guard_skips_parameter_shadow(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "FLAG = True\n\n\ndef run(FLAG):\n    if FLAG:\n        return 1\n    return 0\n",
        encoding="utf-8",
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    assert "dead_guard" not in _kinds(model, "run")


def test_dead_guard_still_fires_on_real_constant(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "ENABLE = False\n\n\ndef run():\n    if ENABLE:\n        return 1\n    return 0\n",
        encoding="utf-8",
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    assert "dead_guard" in _kinds(model, "run")


# --- broad_except_swallow log-only (#8) -------------------------------------


def test_log_only_handler_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "import logging\n\nlogger = logging.getLogger(__name__)\n\n\n"
        "def run():\n"
        "    try:\n"
        "        risky()\n"
        "    except Exception as e:\n"
        "        logger.error(e)\n",
        encoding="utf-8",
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    assert "broad_except_swallow" in _kinds(model, "run")


def test_recovery_handler_is_not_flagged(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "def run():\n"
        "    try:\n"
        "        value = risky()\n"
        "    except Exception:\n"
        "        value = fallback()\n"
        "    return value\n",
        encoding="utf-8",
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    assert "broad_except_swallow" not in _kinds(model, "run")


def test_log_then_reraise_is_not_flagged(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "import logging\n\nlogger = logging.getLogger(__name__)\n\n\n"
        "def run():\n"
        "    try:\n"
        "        risky()\n"
        "    except Exception as e:\n"
        "        logger.error(e)\n"
        "        raise\n",
        encoding="utf-8",
    )
    model = ProjectAnalyzer(tmp_path).analyze(full=True).model
    assert "broad_except_swallow" not in _kinds(model, "run")
