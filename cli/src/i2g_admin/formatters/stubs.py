"""Stub formatters for ``text`` / ``yaml`` / ``csv`` (the U2 seam).

U1 registers the names so ``--output text|yaml|csv`` is a recognized choice with
a clear "not yet available" message instead of an "unknown format" error. U2
replaces each body with a real implementation (and adds the pyyaml dependency)
WITHOUT touching ``formatters/__init__.py``.
"""

from typing import Any

from ..errors import CliError
from . import register


def _unavailable(fmt: str) -> CliError:
    return CliError(f"Output format {fmt!r} is not available in this build yet.")


@register("text")
def _format_text(data: Any) -> str:
    raise _unavailable("text")


@register("yaml")
def _format_yaml(data: Any) -> str:
    raise _unavailable("yaml")


@register("csv")
def _format_csv(data: Any) -> str:
    raise _unavailable("csv")
