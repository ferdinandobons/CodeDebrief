"""Stage 2 single-flow detectors."""

from __future__ import annotations

from pathlib import Path

from logicchart.analysis.python import PythonAnalyzer
from logicchart.analysis.typescript import TypeScriptAnalyzer
from logicchart.config import LogicChartConfig
from logicchart.model import Finding


def _py_findings(tmp_path: Path, body: str) -> list[Finding]:
    source = tmp_path / "module.py"
    source.write_text(body, encoding="utf-8")
    return PythonAnalyzer(tmp_path, LogicChartConfig()).analyze(source).findings


def _ts_route_findings(tmp_path: Path, body: str) -> list[Finding]:
    route = tmp_path / "app" / "api" / "x"
    route.mkdir(parents=True)
    source = route / "route.ts"
    source.write_text(body, encoding="utf-8")
    return TypeScriptAnalyzer(tmp_path, LogicChartConfig()).analyze(source).findings


def _kinds(findings: list[Finding]) -> set[str]:
    return {finding.kind for finding in findings}


# --- missing_branch (flagship) ---------------------------------------------


def test_missing_branch_fires_on_if_elif_chain(tmp_path: Path) -> None:
    findings = _py_findings(
        tmp_path,
        """
def route(account):
    if account.status == Status.ACTIVE:
        return ok()
    elif account.status == Status.SUSPENDED:
        return blocked()
""",
    )
    assert "missing_branch" in _kinds(findings)


def test_missing_branch_silent_on_single_if_guard(tmp_path: Path) -> None:
    findings = _py_findings(
        tmp_path,
        """
def route(account):
    if account.status == Status.SUSPENDED:
        raise Error()
    return ok()
""",
    )
    assert "missing_branch" not in _kinds(findings)


def test_missing_branch_silent_on_if_elif_with_else(tmp_path: Path) -> None:
    findings = _py_findings(
        tmp_path,
        """
def route(account):
    if account.status == Status.ACTIVE:
        return ok()
    elif account.status == Status.SUSPENDED:
        return blocked()
    else:
        return other()
""",
    )
    assert "missing_branch" not in _kinds(findings)


# --- dead code / dead join --------------------------------------------------


def test_dead_code_after_return(tmp_path: Path) -> None:
    findings = _py_findings(
        tmp_path,
        """
def route(x):
    return ok()
    log("never runs")
""",
    )
    assert "dead_code" in _kinds(findings)


def test_dead_join_after_terminating_if_else(tmp_path: Path) -> None:
    findings = _py_findings(
        tmp_path,
        """
def route(flag):
    if flag.status == State.A:
        return a()
    else:
        return b()
    cleanup()
""",
    )
    assert "dead_code" in _kinds(findings)


# --- broad-except swallow ---------------------------------------------------


def test_broad_except_swallow(tmp_path: Path) -> None:
    findings = _py_findings(
        tmp_path,
        """
def route(x):
    try:
        do_work()
    except Exception:
        pass
""",
    )
    assert "broad_except_swallow" in _kinds(findings)


def test_except_that_reraises_is_not_swallow(tmp_path: Path) -> None:
    findings = _py_findings(
        tmp_path,
        """
def route(x):
    try:
        do_work()
    except Exception:
        raise
""",
    )
    assert "broad_except_swallow" not in _kinds(findings)


# --- no-op branch -----------------------------------------------------------


def test_no_op_branch(tmp_path: Path) -> None:
    findings = _py_findings(
        tmp_path,
        """
def route(account):
    if account.status == Status.PENDING:
        pass
    else:
        return handle()
""",
    )
    assert "no_op_branch" in _kinds(findings)


# --- asymmetric return ------------------------------------------------------


def test_asymmetric_return_in_switch(tmp_path: Path) -> None:
    findings = _ts_route_findings(
        tmp_path,
        """
export async function POST(request: Request) {
  switch (order.status) {
    case OrderStatus.PAID:
      return paid();
    case OrderStatus.SHIPPED:
      return shipped();
    case OrderStatus.CANCELLED:
      logCancelled();
    default:
      return fallback();
  }
}
""",
    )
    assert "asymmetric_return" in _kinds(findings)


def test_switch_where_all_cases_return_is_symmetric(tmp_path: Path) -> None:
    findings = _ts_route_findings(
        tmp_path,
        """
export async function POST(request: Request) {
  switch (order.status) {
    case OrderStatus.PAID:
      return paid();
    case OrderStatus.SHIPPED:
      return shipped();
    default:
      return fallback();
  }
}
""",
    )
    assert "asymmetric_return" not in _kinds(findings)


# --- false-positive regressions and ceilings --------------------------------


def test_sequential_same_subject_guards_are_not_a_chain(tmp_path: Path) -> None:
    # Two separate `if` guards (not elif) must not be fused into an elif chain.
    findings = _py_findings(
        tmp_path,
        """
def route(account):
    if account.status == Status.SUSPENDED:
        return blocked()
    if account.status == Status.DELETED:
        return gone()
    return ok()
""",
    )
    assert "missing_branch" not in _kinds(findings)


def test_no_dead_code_after_match_without_default(tmp_path: Path) -> None:
    # Code after a no-default match runs when the value matches nothing.
    findings = _py_findings(
        tmp_path,
        """
def route(order):
    match order.status:
        case Status.PAID:
            return paid()
        case Status.SHIPPED:
            return shipped()
    return fallback()
""",
    )
    assert "dead_code" not in _kinds(findings)


def test_no_dead_code_in_finally_after_return(tmp_path: Path) -> None:
    # A finally block always runs, even when the body returned.
    findings = _py_findings(
        tmp_path,
        """
def route(x):
    try:
        return do_work()
    finally:
        cleanup()
""",
    )
    assert "dead_code" not in _kinds(findings)


def test_dead_code_after_try_finally_that_returns(tmp_path: Path) -> None:
    # The finally runs, then the try's return resumes: code after the try is dead.
    findings = _py_findings(
        tmp_path,
        """
def route(x):
    try:
        return do_work()
    finally:
        cleanup()
    log("after")
""",
    )
    assert "dead_code" in _kinds(findings)


def test_missing_branch_exact_count_on_chain(tmp_path: Path) -> None:
    findings = _py_findings(
        tmp_path,
        """
def route(account):
    if account.status == Status.ACTIVE:
        return ok()
    elif account.status == Status.SUSPENDED:
        return blocked()
""",
    )
    assert len([f for f in findings if f.kind == "missing_branch"]) == 1


def test_complete_if_elif_else_flow_has_no_findings(tmp_path: Path) -> None:
    findings = _py_findings(
        tmp_path,
        """
def route(account):
    if account.status == Status.ACTIVE:
        return ok()
    elif account.status == Status.SUSPENDED:
        return blocked()
    else:
        return other()
""",
    )
    assert findings == []


def test_no_op_silent_on_real_branch(tmp_path: Path) -> None:
    findings = _py_findings(
        tmp_path,
        """
def route(account):
    if account.status == Status.PENDING:
        notify()
    else:
        return handle()
""",
    )
    assert "no_op_branch" not in _kinds(findings)
