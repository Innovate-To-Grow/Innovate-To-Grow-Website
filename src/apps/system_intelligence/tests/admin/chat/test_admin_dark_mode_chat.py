import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


class ChatDarkModeStylesTests(SimpleTestCase):
    """Guard the admin chat CSS against bare light colors that break dark mode.

    Dark mode is driven by a ``.dark`` class on ``<html>``. The admin maps
    Material 3 ``--md-sys-color-*`` tokens (defined for both ``:root`` and
    ``.dark`` in google-material-admin.css) onto these classes, so any color
    must come through a token to flip correctly. A raw light hex with no
    ``.dark`` override renders wrong in dark mode.
    """

    def _read(self, static_path):
        path = finders.find(static_path)
        self.assertIsNotNone(path, f"Could not resolve static asset: {static_path}")
        return Path(path).read_text()

    def test_layout_sidebar_border_uses_outline_variant_token(self):
        source = self._read("system_intelligence/css/chat-layout.css")

        # The mobile (max-width: 900px) sidebar border was a bare light hex
        # (#dbe3ee) with no dark override; it must use the shared token.
        self.assertNotIn("#dbe3ee", source)

        # Scope the assertion to the mobile-only .si-chat-sidebar rule (which
        # drops the right border and sets a bottom border) so the regression
        # guard does not pass on the unrelated header/toolbar border rule.
        mobile_sidebar_rule = re.search(
            r"\.si-chat-sidebar\s*\{[^}]*?border-right:\s*0;[^}]*?\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(mobile_sidebar_rule, "Could not locate the mobile .si-chat-sidebar rule")
        self.assertIn(
            "border-bottom: 1px solid var(--md-sys-color-outline-variant",
            mobile_sidebar_rule.group(0),
        )

    def test_layout_surfaces_use_material_tokens(self):
        source = self._read("system_intelligence/css/chat-layout.css")

        self.assertIn("var(--md-sys-color-surface", source)
        self.assertIn("var(--md-sys-color-outline-variant", source)

    def test_components_colors_use_material_tokens(self):
        source = self._read("system_intelligence/css/chat-components.css")

        self.assertIn("var(--md-sys-color-surface", source)
        self.assertIn("var(--md-sys-color-on-surface", source)

    def test_sidebar_colors_use_material_tokens(self):
        source = self._read("system_intelligence/css/chat-sidebar.css")

        self.assertIn("var(--md-sys-color-surface", source)
        self.assertIn("var(--md-sys-color-outline-variant", source)
