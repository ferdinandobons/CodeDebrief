"""Language analyzers and project-level linking."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logicchart.analysis.project import AnalysisResult, ProjectAnalyzer

__all__ = ["AnalysisResult", "ProjectAnalyzer"]


def __getattr__(name: str) -> object:
    if name in __all__:
        from logicchart.analysis.project import AnalysisResult, ProjectAnalyzer

        return {"AnalysisResult": AnalysisResult, "ProjectAnalyzer": ProjectAnalyzer}[name]
    raise AttributeError(f"module 'logicchart.analysis' has no attribute {name!r}")
