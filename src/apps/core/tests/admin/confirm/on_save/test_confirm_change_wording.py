"""The add / change / delete confirmation page says what is about to happen with a verb ("You are about to change
CMS Embed Allowed Host: …", not "about to changing"); the title keeps "Confirm Adding / Changing / Deleting …", and
any other pending change is "about to modify"."""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.cms.models import CMSEmbedAllowedHost
from apps.core.tests.admin.confirm.on_save.test_confirm_on_save import CHANGE_SESSION_KEY, _make_superuser

MODEL = "CMS Embed Allowed Host"


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ConfirmChangeWordingTest(TestCase):
    def setUp(self):
        _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.host = CMSEmbedAllowedHost.objects.create(hostname="original.com", is_active=True)
        self.confirm_url = reverse("admin:cms_cmsembedallowedhost_confirm_change")

    def confirmation_page(self, url, data):
        response = self.client.post(url, data)
        self.assertRedirects(response, self.confirm_url, fetch_redirect_response=False)
        return self.client.get(self.confirm_url)

    def test_a_change(self):
        url = reverse("admin:cms_cmsembedallowedhost_change", args=[self.host.pk])

        page = self.confirmation_page(url, {"hostname": "changed.com", "is_active": True})

        self.assertEqual(page.context["action_verb"], "change")
        self.assertContains(page, f"You are about to change {MODEL}: <strong>changed.com</strong>")
        self.assertNotContains(page, "You are about to changing")
        self.assertContains(page, f"Confirm Changing {MODEL}")

    def test_an_addition(self):
        page = self.confirmation_page(
            reverse("admin:cms_cmsembedallowedhost_add"), {"hostname": "new-host.com", "is_active": True}
        )

        self.assertEqual(page.context["action_verb"], "add")
        self.assertContains(page, f"You are about to add {MODEL}: <strong>{MODEL}</strong>")
        self.assertNotContains(page, "You are about to adding")

    def test_a_deletion(self):
        url = reverse("admin:cms_cmsembedallowedhost_delete", args=[self.host.pk])

        page = self.confirmation_page(url, {"post": "yes"})

        self.assertEqual(page.context["action_verb"], "delete")
        self.assertContains(page, f"You are about to delete {MODEL}: <strong>original.com</strong>")
        self.assertNotContains(page, "You are about to deleting")

    def test_any_other_pending_change_is_to_modify(self):
        session = self.client.session
        session[CHANGE_SESSION_KEY] = {"token": "t", "action": "import", "object_repr": "hosts.csv", "diff": []}
        session.save()

        page = self.client.get(self.confirm_url)

        self.assertContains(page, f"You are about to modify {MODEL}: <strong>hosts.csv</strong>")
        self.assertContains(page, f"Confirm Modifying {MODEL}")
