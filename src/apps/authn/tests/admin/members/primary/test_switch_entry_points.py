"""Where the switch starts (the member page's button and row links, the Contact Emails action) and what the page
says about signing in and newsletters."""

from django.contrib.messages import get_messages
from django.db import connection
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .fixtures import SwitchFixture, change_url, switch_url

EMAILS = reverse("admin:authn_contactemail_changelist")


def texts(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class MemberPageEntryPointTests(SwitchFixture):
    def test_the_member_page_offers_the_button_and_a_link_on_each_verified_row(self):
        response = self.client.get(change_url(self.jane))

        # The "Switch primary email" button at the top (the row links carry ``?to=``).
        self.assertContains(response, f'href="{switch_url(self.jane)}"')
        self.assertContains(response, f"{switch_url(self.jane)}?to={self.secondary.pk}")
        self.assertContains(response, "Make primary…")
        self.assertContains(response, "Current primary")
        self.assertContains(response, "Verify first")
        self.assertNotContains(response, f"?to={self.unverified.pk}")

    def test_a_helper_sees_neither_on_another_staff_account(self):
        self.client.force_login(self.helper)

        response = self.client.get(change_url(self.staffer))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, switch_url(self.staffer))
        self.assertNotContains(response, "Make primary…")

    def test_a_helper_sees_both_on_a_regular_member(self):
        self.client.force_login(self.helper)

        response = self.client.get(change_url(self.jane))

        self.assertContains(response, f'href="{switch_url(self.jane)}"')
        self.assertContains(response, f"{switch_url(self.jane)}?to={self.secondary.pk}")

    def test_the_inline_errors_point_at_the_new_button(self):
        from apps.authn.admin.members import inlines

        for message in (
            inlines.PRIMARY_EMAIL_INLINE_EDIT_ERROR,
            inlines.PRIMARY_EMAIL_INLINE_DELETE_ERROR,
            inlines.PRIMARY_EMAIL_INLINE_PROMOTION_ERROR,
        ):
            with self.subTest(message=message):
                self.assertIn("Switch primary email", message)
                self.assertNotIn("Contact Emails admin", message)

    def test_the_add_page_has_no_switch(self):
        response = self.client.get(reverse("admin:authn_member_add"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "switch-primary")

    def test_deciding_on_the_button_does_not_load_the_whole_member_again(self):
        model_admin = self.client.get(change_url(self.jane)).context["adminform"].model_admin
        request = RequestFactory().get(change_url(self.jane))
        request.user = self.master

        with CaptureQueriesContext(connection) as queries:
            actions = model_admin.get_actions_detail(request, str(self.jane.pk))

        self.assertEqual([item.action_name for item in actions], ["authn_member_switch_primary_email"])
        # One small query: no profile image, no prefetched contacts.
        self.assertEqual(len(queries), 1, [query["sql"] for query in queries])
        self.assertNotIn("profile_image", queries[0]["sql"])
        self.assertEqual(model_admin.get_actions_detail(request, "not-a-member-id"), [])
