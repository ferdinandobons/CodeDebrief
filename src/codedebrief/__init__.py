"""CodeDebrief turns source code into source-grounded workflow flowcharts."""

from importlib.metadata import PackageNotFoundError, version

from codedebrief.model import ProjectModel

__all__ = ["ProjectModel"]

try:
    __version__ = version("codedebrief")
except PackageNotFoundError:  # pragma: no cover - only when imported outside an install.
    __version__ = "0.0.0"
