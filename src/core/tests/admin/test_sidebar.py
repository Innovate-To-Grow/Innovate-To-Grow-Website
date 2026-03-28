from django.conf import settings
from django.test import SimpleTestCase


class AdminSidebarNavigationTest(SimpleTestCase):
    def test_ses_navigation_includes_ses_entries(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        ses_section = next(section for section in navigation if section["title"] == "Amazon Simple Email Service")
        item_titles = {item["title"] for item in ses_section["items"]}

        self.assertIn("SES Mail Senders", item_titles)
        self.assertIn("SES Compose", item_titles)
        self.assertIn("SES Email Logs", item_titles)

    def test_gmail_navigation_includes_gmail_entries(self):
        navigation = settings.UNFOLD["SIDEBAR"]["navigation"]
        gmail_section = next(section for section in navigation if section["title"] == "Gmail")
        item_titles = {item["title"] for item in gmail_section["items"]}

        self.assertIn("Gmail API Accounts", item_titles)
        self.assertIn("Inbox", item_titles)
        self.assertIn("Sent Mail", item_titles)
        self.assertIn("Compose", item_titles)
        self.assertIn("Email Logs", item_titles)
