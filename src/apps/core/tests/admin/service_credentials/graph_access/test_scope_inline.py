from apps.core.tests.admin.service_credentials.graph_config.test_graph_provider_guard import (
    GuardFixture,
    Permission,
    change_data,
    change_url,
)
from apps.event.tests.helpers import make_admin


class ScopeInlineTests(GuardFixture):
    def test_two_rows_for_one_mailbox_in_different_case_are_a_form_error(self):
        self.email.provider = "ses"
        self.email.save()
        new_scopes = [("Alias@Contoso.com", Permission.SEND), ("alias@contoso.com", Permission.READ)]

        response = self.post(self.config, change_data(self.config, new_scopes=new_scopes))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please correct the duplicate data for mailbox")
        self.assertEqual(self.config.mailbox_scopes.count(), 1)

    def test_a_new_row_that_repeats_a_stored_mailbox_in_another_case_is_a_form_error(self):
        response = self.post(self.config, change_data(self.config, new_scopes=[("I2G@Contoso.com", "send")]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please correct the duplicate data for mailbox")

    def test_any_admin_can_see_and_edit_the_scope(self):
        self.client.force_login(make_admin(email="other-admin@example.com"))

        page = self.client.get(change_url(self.config))
        self.assertContains(page, 'name="mailbox_scopes-TOTAL_FORMS"')
        response = self.post(self.config, change_data(self.config, new_scopes=[("alias@contoso.com", "send")]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.config.mailbox_scopes.filter(mailbox="alias@contoso.com").exists())

    def test_any_admin_is_held_to_the_same_guard(self):
        self.client.force_login(make_admin(email="other-admin@example.com"))

        self.assert_refused(self.post(self.config, change_data(self.config) | {"mailbox_scopes-0-DELETE": "on"}))
