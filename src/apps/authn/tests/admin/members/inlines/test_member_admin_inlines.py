"""Submitting the member admin's contact inlines (UUID-keyed rows, primary-email rules)."""

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail

from .inline_helpers import Member


class _MemberAdminInlineUUIDSubmitCase(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.admin = Member.objects.create_superuser(
            password="admin123",
            first_name="Admin",
            last_name="User",
            is_staff=True,
            is_active=True,
        )
        ContactEmail.objects.create(
            member=self.admin,
            email_address="admin@example.com",
            email_type="primary",
            verified=True,
        )
        self.target = Member.objects.create_user(
            password="target123",
            first_name="Target",
            last_name="User",
            is_active=True,
        )

    # noinspection PyPep8Naming,PyMethodMayBeStatic
    def tearDown(self):
        cache.clear()

    def _change_url(self):
        return f"/admin/authn/member/{self.target.pk}/change/"

    def _build_post_data(self, extra_inline_data=None):
        """Load the admin change page, scrape every <input> value, merge
        inline overrides, and return a dict ready for ``self.client.post``.
        """
        resp = self.client.get(self._change_url())
        self.assertEqual(resp.status_code, 200)

        from html.parser import HTMLParser

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

        if extra_inline_data:
            fields.update(extra_inline_data)

        fields.pop("_addanother", None)
        fields.pop("_continue", None)
        fields["_save"] = "Save"
        return fields


@override_settings(ROOT_URLCONF="config.routing.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class MemberAdminInlineUUIDSubmitTest(_MemberAdminInlineUUIDSubmitCase):
    """Submitting inline forms with UUID PKs must not break on 'None' values.

    Django inline formsets send the literal string "None" for empty UUID
    hidden fields (id, member FK) when adding a new row.  Without the
    NoneSafeUUIDField fix the form returns a validation error:
        "None" is not a valid UUID.
    """

    def test_add_contact_email_with_none_id_does_not_crash(self):
        """Adding a new inline row sends id='None' — must not produce UUID error."""
        self.client.force_login(self.admin)
        data = self._build_post_data(
            {
                "contact_emails-TOTAL_FORMS": "1",
                "contact_emails-INITIAL_FORMS": "0",
                "contact_emails-0-id": "None",
                "contact_emails-0-member": "None",
                "contact_emails-0-email_address": "new@example.com",
                "contact_emails-0-email_type": "primary",
                "contact_emails-0-verified": "",
                "contact_emails-0-subscribe": "on",
            }
        )
        resp = self.client.post(self._change_url(), data)
        content = resp.content.decode() if resp.status_code == 200 else ""
        self.assertNotIn("is not a valid UUID", content)

    def test_edit_existing_primary_status_with_valid_uuid_works(self):
        """Operational status fields remain editable on a primary email."""
        email = ContactEmail.objects.create(
            member=self.target,
            email_address="existing@example.com",
            email_type="primary",
            verified=False,
        )
        self.client.force_login(self.admin)
        data = self._build_post_data(
            {
                "contact_emails-TOTAL_FORMS": "1",
                "contact_emails-INITIAL_FORMS": "1",
                "contact_emails-0-id": str(email.pk),
                "contact_emails-0-member": str(self.target.pk),
                "contact_emails-0-email_address": "existing@example.com",
                "contact_emails-0-email_type": "primary",
                "contact_emails-0-verified": "on",
                "contact_emails-0-subscribe": "on",
            }
        )
        resp = self.client.post(self._change_url(), data)
        content = resp.content.decode() if resp.status_code == 200 else ""
        self.assertNotIn("is not a valid UUID", content)
        email.refresh_from_db()
        self.assertEqual(email.email_type, "primary")
        self.assertTrue(email.verified)
