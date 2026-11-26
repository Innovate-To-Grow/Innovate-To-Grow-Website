from html.parser import HTMLParser

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail, Member


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class MemberAdminChangePageTests(TestCase):
    """Exercise the real admin change page through the test client.

    ``ADMIN_REQUIRE_CONFIRMATION=False`` skips the confirm-on-save interstitial
    so the POST commits directly (matching the inline-submit test class), letting
    us assert persistence of the **Admin** switch.
    """

    def setUp(self):
        cache.clear()
        self.admin = Member.objects.create_user(
            password="StrongPass123!", first_name="Ada", last_name="Admin", is_staff=True, is_active=True
        )
        ContactEmail.objects.create(
            member=self.admin, email_address="ada@example.com", email_type="primary", verified=True
        )
        self.target = Member.objects.create_user(
            password="StrongPass123!", first_name="Target", last_name="User", is_staff=True, is_active=True
        )
        ContactEmail.objects.create(
            member=self.target, email_address="target@example.com", email_type="primary", verified=True
        )
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def _change_url(self):
        return f"/admin/authn/member/{self.target.pk}/change/"

    def test_change_page_has_one_admin_switch(self):
        resp = self.client.get(self._change_url())
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('name="is_staff"', content)
        self.assertIn("Admin access", content)
        self.assertIn("All Admins have the same permissions.", content)
        for absent in ("admin_apps", "is_superuser", "groups", "user_permissions"):
            with self.subTest(field=absent):
                self.assertNotIn(f'name="{absent}"', content)
                self.assertNotIn(f'id="id_{absent}"', content)
        self.assertNotIn("Staff status", content)

    def test_unticking_admin_makes_a_regular_member(self):
        data = build_change_post_data(self.client, self._change_url())
        data.pop("is_staff", None)
        resp = self.client.post(self._change_url(), data)
        # 302 = a successful save+redirect; a 200 would mean the form re-rendered
        # with errors and never committed, so assert the redirect explicitly.
        self.assertEqual(resp.status_code, 302, resp.content.decode())
        self.target.refresh_from_db()
        self.assertEqual((self.target.is_staff, self.target.is_superuser), (False, False))

    def test_a_posted_superuser_flag_is_ignored(self):
        Member.objects.filter(pk=self.target.pk).update(is_staff=False, is_superuser=False)
        data = build_change_post_data(self.client, self._change_url(), {"is_superuser": "on"})
        resp = self.client.post(self._change_url(), data)
        self.assertEqual(resp.status_code, 302, resp.content.decode())
        self.target.refresh_from_db()
        self.assertEqual((self.target.is_staff, self.target.is_superuser), (False, False))


def build_change_post_data(client, url, overrides=None):
    """Scrape a Member change page's form inputs into a POST-ready dict (the form submitted unchanged).

    Mirrors the helper in test_member_admin_inlines so the round-trip
    submits a complete, valid Member change form.
    """
    resp = client.get(url)
    assert resp.status_code == 200, resp.status_code

    fields: dict[str, str] = {}
    textarea_name: str | None = None
    select_name: str | None = None
    selected_value: str | None = None

    class _FormParser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            nonlocal textarea_name, select_name, selected_value
            attr = dict(attrs)
            name = attr.get("name")
            if tag == "input" and name:
                if attr.get("type") == "checkbox":
                    if "checked" in attr:
                        fields[name] = attr.get("value", "on")
                else:
                    fields.setdefault(name, attr.get("value", ""))
            elif tag == "textarea" and name:
                textarea_name = name
            elif tag == "select" and name:
                select_name = name
            elif tag == "option" and select_name and "selected" in attr:
                selected_value = attr.get("value", "")

        def handle_data(self, data):
            nonlocal textarea_name
            if textarea_name:
                fields.setdefault(textarea_name, data.strip())

        def handle_endtag(self, tag):
            nonlocal textarea_name, select_name, selected_value
            if tag == "textarea":
                textarea_name = None
            elif tag == "select" and select_name:
                if selected_value is not None:
                    fields.setdefault(select_name, selected_value)
                select_name = None
                selected_value = None

    parser = _FormParser()
    parser.feed(resp.content.decode())

    # No inline rows for this round-trip.
    for prefix in ("contact_emails", "contact_phones"):
        fields.setdefault(f"{prefix}-TOTAL_FORMS", "0")
        fields.setdefault(f"{prefix}-INITIAL_FORMS", "0")
        fields.setdefault(f"{prefix}-MIN_NUM_FORMS", "0")
        fields.setdefault(f"{prefix}-MAX_NUM_FORMS", "1000")

    if overrides:
        fields.update(overrides)

    fields.pop("_addanother", None)
    fields.pop("_continue", None)
    fields["_save"] = "Save"
    return fields
