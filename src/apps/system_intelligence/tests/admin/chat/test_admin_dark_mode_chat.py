import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

# Colors that may legitimately appear as a direct (non-token) value: pure
# black/white and alpha-bearing rgba() shadows/tints are mode-neutral. Anything
# else used as a raw value (not a var() fallback) is a light-only color that
# will not flip under .dark — the bug class this guard exists to catch.
_NEUTRAL_HEX = {"#000", "#fff", "#000000", "#ffffff"}


def _hex_is_var_fallback(text, hex_start):
    """True when the hex at ``hex_start`` sits inside a ``var(--token, #hex)`` call."""
    depth = 0
    i = hex_start - 1
    while i >= 0:
        char = text[i]
        if char == ")":
            depth += 1
        elif char == "(":
            if depth == 0:
                return text[max(0, i - 3) : i] == "var"
            depth -= 1
        i -= 1
    return False


def _raw_light_hexes(source):
    """Hex colors used as direct values (not var() fallbacks, not neutral)."""
    return [
        match.group(0)
        for match in re.finditer(r"#[0-9a-fA-F]{3,6}", source)
        if match.group(0).lower() not in _NEUTRAL_HEX and not _hex_is_var_fallback(source, match.start())
    ]


class ChatDarkModeStylesTests(SimpleTestCase):
    """Guard the admin chat CSS against bare light colors that break dark mode.

    Dark mode is driven by a ``.dark`` class on ``<html>``. The admin maps
    Material 3 ``--md-sys-color-*`` tokens (defined for both ``:root`` and
    ``.dark`` in google-material-admin.css) onto these classes, so any color
    must come through a token to flip correctly. A raw light hex used as a
    direct value (with no ``.dark`` override) renders wrong in dark mode — these
    tests fail if any such color is (re)introduced, so they would catch a revert
    of the ``#dbe3ee`` fix rather than passing vacuously.
    """

    CHAT_CSS = (
        "system_intelligence/css/chat-layout.css",
        "system_intelligence/css/chat-components.css",
        "system_intelligence/css/chat-sidebar.css",
    )

    def _read(self, static_path):
        path = finders.find(static_path)
        self.assertIsNotNone(path, f"Could not resolve static asset: {static_path}")
        return Path(path).read_text()

    def test_no_chat_css_uses_a_raw_light_hex_value(self):
        for static_path in self.CHAT_CSS:
            with self.subTest(stylesheet=static_path):
                raw = _raw_light_hexes(self._read(static_path))
                self.assertEqual(
                    raw,
                    [],
                    f"{static_path} uses raw light hex value(s) {raw} with no token; "
                    "they will not flip under the .dark class.",
                )

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
