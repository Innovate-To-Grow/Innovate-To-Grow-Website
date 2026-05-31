"""Page-freeze service: capture an external page as a self-contained HTML document.

Ports the static path of the standalone ``webfreeze`` tool into the CMS, with an
added SSRF guard (admin-supplied URLs) and section-removal support. Output is a
single self-contained HTML string (CSS inlined as ``<style>``, images/fonts as
base64) intended to be served into a sandboxed iframe.
"""

from .config import REMOVAL_PRESET_KEYS, REMOVAL_PRESETS
from .exceptions import BlockedURLError, FreezeError, FreezeFetchError
from .orchestrator import FrozenResult, freeze_url

__all__ = [
    "REMOVAL_PRESETS",
    "REMOVAL_PRESET_KEYS",
    "BlockedURLError",
    "FreezeError",
    "FreezeFetchError",
    "FrozenResult",
    "freeze_url",
]
