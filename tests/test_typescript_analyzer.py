from pathlib import Path

from logicchart.analysis.typescript import TypeScriptAnalyzer
from logicchart.config import LogicChartConfig
from logicchart.model import NodeKind


def test_next_route_and_switch_are_detected(tmp_path: Path) -> None:
    route_dir = tmp_path / "app" / "api" / "users"
    route_dir.mkdir(parents=True)
    source = route_dir / "route.ts"
    source.write_text(
        """
export async function POST(request: Request) {
  const user = await loadUser(request);
  switch (user.status) {
    case UserStatus.ACTIVE:
      return Response.json(user);
    case UserStatus.SUSPENDED:
      throw new Error("blocked");
  }
}
""",
        encoding="utf-8",
    )

    analysis = TypeScriptAnalyzer(tmp_path, LogicChartConfig()).analyze(source)

    assert len(analysis.flows) == 1
    flow = analysis.flows[0]
    assert flow.is_entrypoint
    assert flow.framework == "nextjs"
    assert flow.entry_kind == "route"
    assert any(node.kind is NodeKind.DECISION for node in flow.nodes)
    assert any(item.kind == "missing_branch" for item in analysis.findings)


def test_exported_react_component_is_an_entrypoint(tmp_path: Path) -> None:
    source = tmp_path / "UserPanel.tsx"
    source.write_text(
        """
export function UserPanel({ user }: Props) {
  if (!user.isAuthorized) {
    return <LoginPrompt />;
  }
  return <Dashboard user={user} />;
}
""",
        encoding="utf-8",
    )

    analysis = TypeScriptAnalyzer(tmp_path, LogicChartConfig()).analyze(source)
    flow = analysis.flows[0]

    assert flow.is_entrypoint
    assert flow.framework == "react"
    assert flow.entry_kind == "component"
