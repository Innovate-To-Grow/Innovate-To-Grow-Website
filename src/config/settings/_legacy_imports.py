"""
Legacy-import compatibility shim.

Business apps live under the ``apps`` package (e.g. ``apps.event``), and each
app's ``AppConfig`` keeps its original Django ``label`` (``"event"``) while its
import ``name`` becomes ``"apps.event"``. Migration files — which must never be
edited — still contain module-level ``import event.models...`` style imports.

This meta-path finder transparently aliases a legacy top-level app import
(``event``, ``event.models.registration.ticket``, ...) to the matching
``apps.*`` package and returns the *same* module object (it never re-executes
the module). Because the object is shared, deconstructed field defaults and
managers resolve to identical ``__module__`` strings whether reached through the
live model (``apps.event...``) or through a migration's legacy import — so
``makemigrations --check`` reports no spurious changes.

Safety properties:

* A root is aliased only when ``apps/<root>/`` exists on disk, so this is a
  no-op for apps that have not been moved yet (every intermediate refactor
  commit stays importable).
* ``core`` split its project-config modules (``settings``/``urls``/``wsgi``/
  ``asgi``) out to the ``config`` package; those names are never aliased, so a
  stray ``import core.urls`` fails loudly instead of silently misresolving.
* Installation is idempotent — importing this module repeatedly (settings
  files do ``from .base import *``) never stacks duplicate finders.

This module installs the finder as an import side effect; import it before any
first-party app or migration import (``base.py`` does so on its first line).
"""

import importlib
import sys
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from pathlib import Path

# Original top-level package names that may still appear in migration imports.
_LEGACY_ROOTS = (
    "authn",
    "cms",
    "core",
    "event",
    "mail",
    "projects",
    "system_intelligence",
)

# ``core`` project-config modules that moved to the ``config`` package and must
# never be aliased to ``apps.core.*`` (they do not exist there).
_CORE_CONFIG_DENY = ("core.settings", "core.urls", "core.wsgi", "core.asgi")

# This file lives at ``<src>/<config-package>/settings/_legacy_imports.py`` both
# before (``core/settings/``) and after (``config/settings/``) the config split,
# so ``parents[2]`` is always ``<src>`` and the apps package sits beside it.
_APPS_DIR = Path(__file__).resolve().parents[2] / "apps"


class _LegacyAppLoader(Loader):
    """Loader that aliases a legacy name to an already-built ``apps.*`` module."""

    def __init__(self, canonical_name):
        self._canonical_name = canonical_name

    def create_module(self, spec):
        module = importlib.import_module(self._canonical_name)
        sys.modules[spec.name] = module
        # Capture the canonical spec before the import machinery overwrites
        # ``module.__spec__`` with this legacy-named spec (see exec_module).
        self._canonical_spec = module.__spec__
        return module

    def exec_module(self, module):
        # The canonical module body already executed during import_module above;
        # re-executing here would create a second object and break __module__
        # identity, so we do not re-exec. We only restore __spec__: the import
        # machinery just set module.__spec__ to this loader's legacy-named spec,
        # which would leave __spec__.name out of sync with __name__ (and point a
        # later importlib.reload() at the wrong name). Restoring the canonical
        # spec keeps the shared module object's metadata self-consistent.
        if getattr(self, "_canonical_spec", None) is not None:
            module.__spec__ = self._canonical_spec


class _LegacyAppFinder(MetaPathFinder):
    """Redirect legacy ``<app>.*`` imports to ``apps.<app>.*`` packages."""

    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root not in _LEGACY_ROOTS or fullname.startswith("apps."):
            return None
        if root == "core" and (
            fullname in _CORE_CONFIG_DENY or any(fullname.startswith(name + ".") for name in _CORE_CONFIG_DENY)
        ):
            return None
        if not (_APPS_DIR / root).is_dir():
            return None
        return ModuleSpec(fullname, _LegacyAppLoader("apps." + fullname))


def install():
    """Insert the finder at the front of ``sys.meta_path`` (once)."""
    if not any(isinstance(finder, _LegacyAppFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _LegacyAppFinder())


install()
