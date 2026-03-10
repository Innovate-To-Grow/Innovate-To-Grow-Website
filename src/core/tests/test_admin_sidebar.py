from django.conf import settings
from django.test import SimpleTestCase


class AdminSidebarNavigationTest(SimpleTestCase):
    def test_mail_navigation_includes_ses_entries(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        mail_section = next(section for section in navigation if section["title"] == "Mail")
        item_titles = {item["title"] for item in mail_section["items"]}

        self.assertIn("SES Mail Senders", item_titles)
        self.assertIn("SES Compose", item_titles)
        self.assertIn("SES Email Logs", item_titles)
