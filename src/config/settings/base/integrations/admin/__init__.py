"""Unfold admin settings assembled from theme, tabs, and navigation."""

from .navigation import SIDEBAR as _SIDEBAR
from .tabs import TABS as _TABS
from .theme import UNFOLD_THEME as _UNFOLD_THEME

__all__ = ["UNFOLD"]

UNFOLD = {
    **_UNFOLD_THEME,
    "TABS": _TABS,
    "SIDEBAR": _SIDEBAR,
}
