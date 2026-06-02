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
