"""Dark-mode color/theme regression coverage for the mail admin templates.

Mirrors the patterns in ``apps.core.tests.admin.test_admin_theme``: it logs in as
a superuser and asserts that the inbox loading skeleton no longer uses a raw
light shimmer gradient with no ``.dark`` counterpart (which would render a bright
shimmer over dark admin panels).
"""

from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_superuser

INBOX_LIST_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "admin" / "mail" / "inbox" / "list.html"

# The light shimmer the skeleton ships with. It is intentionally preserved for
# light mode, but on its own (without a ``.dark`` override or token reference) it
# would leak into dark mode as a bright shimmer over dark panels.
LIGHT_SKELETON_GRADIENT = "linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)"


class InboxSkeletonDarkModeTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_inbox_list_renders_for_superuser(self):
        response = self.client.get(reverse("admin:mail_inbox_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "i2g-skel")

    def test_rendered_inbox_skeleton_has_dark_mode_override(self):
        response = self.client.get(reverse("admin:mail_inbox_list"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        # The light gradient stays exactly as-is for light mode.
        self.assertIn(LIGHT_SKELETON_GRADIENT, html)
        # A dark-scoped skeleton override must exist so dark mode does not inherit
        # the light shimmer.
        self.assertIn(".dark .i2g-skel", html)

    def test_template_skeleton_dark_override_uses_surface_tokens(self):
        source = INBOX_LIST_TEMPLATE.read_text()

        # Light mode is unchanged.
        self.assertIn(LIGHT_SKELETON_GRADIENT, source)

        # The dark override exists and is driven by Material surface tokens
        # (defined for both :root and .dark in google-material-admin.css) rather
        # than reusing the light grays.
        dark_index = source.find(".dark .i2g-skel")
        self.assertNotEqual(dark_index, -1, ".dark .i2g-skel override is missing")

        dark_block = source[dark_index : dark_index + 400]
        self.assertIn("var(--md-sys-color-surface-container", dark_block)
        # The light grays must not appear inside the dark override block.
        self.assertNotIn("#f0f0f0", dark_block)
        self.assertNotIn("#e0e0e0", dark_block)
