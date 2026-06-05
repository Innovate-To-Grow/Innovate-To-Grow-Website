import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from apps.core.models import SiteMaintenanceControl
from apps.event.tests.helpers import make_superuser


class AdminThemeRenderingTests(TestCase):
    def assert_persisted_admin_theme_defaults_to_system(self, response):
        html = response.content.decode()
        persisted_state = r"\$persist\(\s*['\"]auto['\"]\s*\)\.as\(\s*['\"]adminTheme['\"]\s*\)"

        if re.search(persisted_state, html):
            return

        self.assertIn("adminTheme", html)
        self.assertIn("adminTheme = 'auto'", html)

    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_unfold_theme_is_not_locked_to_light(self):
        self.assertFalse(settings.UNFOLD.get("THEME"))

    def test_admin_pages_default_to_persisted_system_theme(self):
        config = SiteMaintenanceControl.objects.create(is_maintenance=False)

        response = self.client.get(reverse("admin:core_sitemaintenancecontrol_change", args=[config.pk]))

        self.assertEqual(response.status_code, 200)
        self.assert_persisted_admin_theme_defaults_to_system(response)
        self.assertContains(response, 'data-testid="i2g-admin-theme-toggle"')
        self.assertNotContains(response, '<html lang="en-us" dir="ltr" class="light"')

    def test_authenticated_admin_header_renders_theme_toggle(self):
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="i2g-admin-theme-toggle"')
        self.assertContains(response, 'aria-label="Switch admin theme"')
        self.assertContains(response, 'aria-label="Admin theme options"')
        self.assertContains(response, "light_mode")
        self.assertContains(response, "dark_mode")
        self.assertContains(response, "computer")

    def test_login_page_exposes_unfold_theme_options(self):
        self.client.logout()

        response = self.client.get("/admin/login/")

        self.assertEqual(response.status_code, 200)
        self.assert_persisted_admin_theme_defaults_to_system(response)
        self.assertContains(response, "Light")
        self.assertContains(response, "Dark")
        self.assertContains(response, "System")

    def test_theme_toggle_styles_are_loaded_after_unfold_styles(self):
        response = self.client.get(reverse("admin:index"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertLess(
            html.index("/static/unfold/css/styles.css"),
            html.index("/static/admin/css/google-material-admin-overrides.css"),
        )
        path = finders.find("admin/css/google-material-admin-overrides.css")
        self.assertIsNotNone(path)
        source = Path(path).read_text()
        self.assertIn(".i2g-admin-theme-toggle__button", source)
        self.assertIn(".i2g-admin-theme-toggle__option.is-active", source)

    def test_configured_unfold_styles_are_resolvable_static_assets(self):
        for style_factory in settings.UNFOLD["STYLES"]:
            style_path = style_factory(None).removeprefix("/static/")
            with self.subTest(style_path=style_path):
                self.assertIsNotNone(finders.find(style_path))


class AdminThemeDarkModeTests(TestCase):
    """Dark-mode color/theme coverage for the central admin stylesheets."""

    @staticmethod
    def _read(asset):
        path = finders.find(asset)
        assert path is not None, f"static asset not found: {asset}"
        return Path(path).read_text()

    def test_dark_token_block_is_present(self):
        source = self._read("admin/css/google-material-admin.css")

        # The dark token block redefines every --md-sys-color-* token under a
        # .dark selector, so var(..., #lightfallback) always resolves in dark.
        dark_start = source.index(".dark,")
        self.assertIn("--md-sys-color-surface: #131314", source[dark_start:])
        self.assertIn("--md-sys-color-primary: #a8c7fa", source[dark_start:])
        self.assertIn("--md-sys-color-on-primary: #202124", source[dark_start:])

    def test_broad_bg_white_substring_selector_is_gone(self):
        source = self._read("admin/css/google-material-admin.css")

        # The broad substring match also caught Tailwind translucent overlays
        # (bg-white/20, hover:bg-white/30) on the "select all" bar; the exact
        # whitespace-token selector leaves those to Unfold.
        self.assertNotIn('[class*="bg-white"]', source)
        self.assertIn('[class~="bg-white"]', source)
        self.assertIn('.dark [class~="bg-white"]', source)

    def test_dark_checkbox_checkmark_uses_dark_stroke(self):
        source = self._read("admin/css/google-material-admin-overrides.css")

        # In dark mode the checkbox fill is light blue, so the checkmark needs a
        # dark stroke (matching --md-sys-color-on-primary) for contrast.
        self.assertIn(".dark #changelist input.action-select:checked", source)
        self.assertIn(".dark #changelist input.action-toggle:checked", source)
        dark_check_start = source.index(".dark #changelist input.action-select:checked")
        dark_check_block = source[dark_check_start:]
        self.assertIn("stroke='%23202124'", dark_check_block)
        # The light rule keeps its white stroke unchanged.
        light_check_block = source[: source.index(".dark #changelist input.action-select:checked")]
        self.assertIn("stroke='%23fff'", light_check_block)

    def test_dark_switch_knob_shadow_is_overridden(self):
        source = self._read("admin/css/google-material-admin.css")

        # The white knob is kept (Material convention), but its light drop
        # shadow is replaced by a darker shadow under .dark.
        self.assertIn('.dark input[type="checkbox"].appearance-none.w-8::after', source)
        dark_knob_start = source.index('.dark input[type="checkbox"].appearance-none.w-8::after')
        dark_knob_block = source[dark_knob_start : dark_knob_start + 200]
        self.assertIn("rgba(0, 0, 0, 0.6)", dark_knob_block)

    def test_overrides_still_load_after_unfold_styles(self):
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

        response = self.client.get(reverse("admin:index"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertLess(
            html.index("/static/unfold/css/styles.css"),
            html.index("/static/admin/css/google-material-admin-overrides.css"),
        )
