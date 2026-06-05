"""Dark-mode rendering guards for core admin templates.

These cover the chrome rendered inside admin change forms — the submit-line
autosave toggle, the bulk-export column picker, and the maintenance bypass
password widget — to ensure no light-only styling leaks into dark mode.

Dark mode in this admin is driven by a ``.dark`` class on ``<html>`` (see
``google-material-admin.css``), so any styling that must adapt has to ship a
``.dark``-scoped override rather than relying on ``prefers-color-scheme`` alone.
"""

import re
from pathlib import Path

from django.template.loader import get_template
from django.test import TestCase
from django.urls import reverse

from apps.core.models import SiteMaintenanceControl
from apps.event.tests.helpers import make_superuser


def _template_source(name):
    """Return the on-disk source of a template by template name."""
    template = get_template(name)
    origin = getattr(template, "origin", None) or getattr(template.template, "origin", None)
    assert origin is not None and origin.name, f"Could not resolve origin for template {name!r}"
    return Path(origin.name).read_text()


class AutosaveToggleDarkModeTests(TestCase):
    """The submit-line autosave toggle must read on the dark track."""

    template_name = "admin/includes/itg_submit_line_autosave_style.html"

    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_change_form_renders_autosave_toggle_with_dark_overrides(self):
        config = SiteMaintenanceControl.objects.create(is_maintenance=False)

        response = self.client.get(reverse("admin:core_sitemaintenancecontrol_change", args=[config.pk]))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        # The toggle structure is present on the change form.
        self.assertIn("admin-autosave-switch", html)
        self.assertIn("admin-autosave-knob", html)
        # Dark mode is keyed on the .dark class, so the inline style block must
        # ship .dark-scoped overrides for the track and label.
        self.assertIn(".dark .admin-autosave-switch", html)
        self.assertIn(".dark .admin-autosave-label", html)

    def test_checked_knob_has_dark_override_for_light_primary_track(self):
        source = _template_source(self.template_name)

        # In dark mode --md-sys-color-primary flips to a light blue (#a8c7fa),
        # so a plain white knob washes out against the checked track. The knob
        # must switch to on-primary in dark mode for contrast.
        self.assertIn(
            ".dark .admin-autosave-toggle .admin-autosave-checkbox:checked "
            "+ .admin-autosave-switch .admin-autosave-knob",
            source,
        )
        self.assertIn("var(--md-sys-color-on-primary", source)

    def test_saved_status_color_has_dark_override(self):
        source = _template_source(self.template_name)

        # The "saved" status uses a dark-green light-mode hex (#137333) that has
        # almost no contrast on the dark surface; a .dark override is required.
        self.assertIn(".dark .admin-autosave-status.saved", source)

    def test_light_mode_track_and_knob_are_unchanged(self):
        source = _template_source(self.template_name)

        # Preserve light mode exactly: the base knob stays white and the base
        # checked track keeps the light-mode primary token.
        self.assertIn(".admin-autosave-switch .admin-autosave-knob { width: 18px;", source)
        self.assertIn("background: #fff;", source)
        self.assertIn(
            ".admin-autosave-toggle .admin-autosave-checkbox:checked + .admin-autosave-switch { "
            "background: var(--md-sys-color-primary, #305f9d);",
            source,
        )


class ExportColumnsDarkModeTests(TestCase):
    """The bulk-export column picker must adapt to the .dark class, not just OS preference."""

    template_name = "admin/core/export_columns.html"

    def _style_block(self):
        source = _template_source(self.template_name)
        return source[source.index("<style>") : source.index("</style>")]

    def test_export_template_uses_only_tokenized_colors(self):
        style_block = self._style_block()

        # Every color in the export styles must be expressed as a CSS custom
        # property (md-sys or Unfold color-base tokens), with hex only ever
        # appearing as a var() fallback. Catch any raw hex used as a value.
        raw_hex = [
            match.group(0)
            for match in re.finditer(r"#[0-9a-fA-F]{3,6}", style_block)
            if not _hex_is_var_fallback(style_block, match.start())
        ]
        self.assertEqual(raw_hex, [], f"Raw (non-token) hex colors found in export styles: {raw_hex}")

    def test_export_card_background_uses_surface_tokens(self):
        source = _template_source(self.template_name)

        self.assertIn("var(--md-sys-color-surface-container-lowest", source)
        self.assertIn("var(--md-sys-color-outline-variant", source)

    def test_dark_styling_is_keyed_on_the_dark_class_not_prefers_color_scheme(self):
        # The theme toggle adds `.dark` to <html> regardless of the OS
        # prefers-color-scheme. Unfold's --color-base-* ramp is a FIXED light
        # ramp that does not flip under .dark, so the preview table — which is
        # built on --color-base-* — would render a light island inside the dark
        # card if its dark styling stayed gated on @media (prefers-color-scheme).
        # Guard that the dark overrides are `.dark`-scoped instead.
        style_block = self._style_block()

        self.assertNotIn(
            "@media (prefers-color-scheme: dark)",
            style_block,
            "Export dark styling must be .dark-scoped: @media (prefers-color-scheme) "
            "does not fire when the toggle forces dark on a light-OS machine.",
        )
        # The surfaces that previously only adapted under the media query must
        # now have explicit .dark overrides built on md-sys tokens (which flip).
        for selector in (".dark .export-card", ".dark .preview-table th", ".dark .preview-table td"):
            self.assertIn(selector, style_block, f"Missing dark override for {selector!r}")
        self.assertIn(".dark .preview-table th", style_block)
        self.assertIn("var(--md-sys-color-surface-container-high", style_block)


class MaterialPasswordWidgetDarkModeTests(TestCase):
    """The maintenance bypass password widget must carry no light-only chrome."""

    template_name = "admin/material_password_widget.html"

    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_widget_template_has_no_inline_color_styles(self):
        source = _template_source(self.template_name)

        # The widget defers all coloring to the md-outlined-text-field tokens in
        # the central CSS; it must not hardcode any light background/color.
        self.assertNotIn("background:", source)
        self.assertNotIn("background-color:", source)
        self.assertIn("md-outlined-text-field", source)

    def test_change_form_renders_password_widget(self):
        config = SiteMaintenanceControl.objects.create(is_maintenance=True, bypass_password="secret123")

        response = self.client.get(reverse("admin:core_sitemaintenancecontrol_change", args=[config.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "md-outlined-text-field")


def _hex_is_var_fallback(text, hex_start):
    """True when the hex at ``hex_start`` sits inside a ``var(--token, #hex)`` call."""
    # Walk backwards to the nearest unmatched "(" and confirm it opens a var().
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
