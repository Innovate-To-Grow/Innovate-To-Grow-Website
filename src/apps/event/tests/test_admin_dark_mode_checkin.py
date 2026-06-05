import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from apps.event.models import CheckIn
from apps.event.tests.helpers import make_event, make_superuser


def _read_static(relative_path):
    path = finders.find(relative_path)
    assert path is not None, f"static asset not found: {relative_path}"
    return Path(path).read_text()


class CheckInConsoleDarkModeTests(TestCase):
    """The fullscreen kiosk console must support admin dark mode.

    The scanner console extends admin/base_site.html, so the admin sets a
    `.dark` class on <html> in dark mode. Without a `.dark` override the kiosk
    stays light (white panels / dark text) inside the dark shell. These tests
    pin the tokenized palette and the dark override so light mode stays
    pixel-identical while dark mode is readable.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = _read_static("event/css/checkin_console.css")

    def test_light_root_palette_is_preserved(self):
        # Light kiosk values must stay exactly as shipped.
        self.assertIn("--checkin-panel: #ffffff;", self.css)
        self.assertIn("--checkin-bg: #f7f8fb;", self.css)
        self.assertIn("--checkin-blue: #123a5f;", self.css)
        self.assertIn("--checkin-success: #067647;", self.css)
        self.assertIn("--checkin-error: #b42318;", self.css)

    def test_key_surfaces_are_tokenized(self):
        # Surfaces/text/borders/status backgrounds must flow through variables
        # so the dark override can flip them. New tokens introduced by the fix.
        self.assertIn("--checkin-text:", self.css)
        self.assertIn("--checkin-text-secondary:", self.css)
        self.assertIn("--checkin-subtle-bg:", self.css)
        self.assertIn("--checkin-row-border:", self.css)
        self.assertIn("--checkin-success-border:", self.css)
        self.assertIn("--checkin-preview-bg:", self.css)
        # The console text color should reference the token, not a raw hex.
        self.assertIn("color: var(--checkin-text);", self.css)

    def test_no_raw_hex_outside_variable_block(self):
        # Every raw hex color must live in the :root/top variable declarations,
        # i.e. on a line that declares a --checkin-* custom property. CSS
        # comments (which document the dark palette) are stripped first.
        source = re.sub(r"/\*.*?\*/", "", self.css, flags=re.DOTALL)
        for line in source.splitlines():
            if "#" not in line:
                continue
            stripped = line.strip()
            if stripped.startswith("--checkin-"):
                continue
            self.assertNotRegex(
                stripped,
                r"#[0-9a-fA-F]{3,8}\b",
                msg=f"raw hex color used outside the variable block: {stripped!r}",
            )

    def test_dark_override_block_exists_and_flips_surfaces(self):
        self.assertIn(".dark .i2g-checkin-console", self.css)
        dark_block = self.css.split(".dark .i2g-checkin-console", 1)[1]
        # Dark surfaces / text / borders mirror the central Material theme.
        self.assertIn("--checkin-panel: #202124;", dark_block)
        self.assertIn("--checkin-bg: #131314;", dark_block)
        self.assertIn("--checkin-text: #e8eaed;", dark_block)
        self.assertIn("--checkin-border: #444746;", dark_block)
        # Status text flips lighter (error mirrors central #ffb4ab).
        self.assertIn("--checkin-error: #ffb4ab;", dark_block)


class CheckInSummaryDarkModeTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = _read_static("event/css/checkin_change_summary.css")

    def test_light_root_palette_is_preserved(self):
        self.assertIn("--checkin-summary-panel: #ffffff;", self.css)
        self.assertIn("--checkin-summary-bg: #eff6ff;", self.css)
        self.assertIn("--checkin-summary-primary: #0f4f8f;", self.css)
        self.assertIn("--checkin-summary-success: #067647;", self.css)

    def test_key_surfaces_are_tokenized(self):
        self.assertIn("--checkin-summary-text:", self.css)
        self.assertIn("--checkin-summary-on-primary:", self.css)
        self.assertIn("--checkin-summary-inner-border:", self.css)
        self.assertIn("--checkin-summary-input-bg:", self.css)
        self.assertIn("--checkin-summary-input-border:", self.css)
        # Root text references the token rather than a raw hex.
        self.assertIn("color: var(--checkin-summary-text);", self.css)

    def test_dark_override_covers_every_surface_variable(self):
        self.assertIn(".dark .i2g-checkin-summary", self.css)
        dark_block = self.css.split(".dark .i2g-checkin-summary", 1)[1]
        for token in (
            "--checkin-summary-bg:",
            "--checkin-summary-panel:",
            "--checkin-summary-border:",
            "--checkin-summary-muted:",
            "--checkin-summary-text:",
            "--checkin-summary-primary:",
            "--checkin-summary-primary-strong:",
            "--checkin-summary-on-primary:",
            "--checkin-summary-inner-border:",
            "--checkin-summary-input-bg:",
            "--checkin-summary-input-border:",
            "--checkin-summary-success:",
            "--checkin-summary-warning:",
            "--checkin-summary-error:",
        ):
            with self.subTest(token=token):
                self.assertIn(token, dark_block)

    def test_dark_surfaces_mirror_central_theme(self):
        dark_block = self.css.split(".dark .i2g-checkin-summary", 1)[1]
        self.assertIn("--checkin-summary-panel: #202124;", dark_block)
        self.assertIn("--checkin-summary-bg: #131314;", dark_block)
        self.assertIn("--checkin-summary-text: #e8eaed;", dark_block)
        self.assertIn("--checkin-summary-border: #444746;", dark_block)
        self.assertIn("--checkin-summary-error: #ffb4ab;", dark_block)


class CheckInScannerPageRendersDarkAwareConsoleTests(TestCase):
    """The scanner console page loads the dark-aware stylesheet under the
    admin shell that toggles `.dark`."""

    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.event = make_event(name="Dark Mode Demo Day")
        self.check_in = CheckIn.objects.create(event=self.event, name="Front Desk")

    def test_scanner_console_loads_console_stylesheet(self):
        url = reverse("admin:event_checkin_scanner", args=[self.check_in.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "event/css/checkin_console.css")
        self.assertContains(response, "i2g-checkin-console")
