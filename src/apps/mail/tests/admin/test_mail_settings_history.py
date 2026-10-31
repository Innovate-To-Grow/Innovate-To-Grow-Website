"""Notification Delivery saves leave admin history: who changed which fields, never the values."""

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, MicrosoftGraphProviderConfig, SMTPProviderConfig

from .test_mail_settings_admin_graph import GraphSettingsTestCase


class NotificationDeliveryHistoryTests(GraphSettingsTestCase):
    def entries(self, model):
        return LogEntry.objects.filter(content_type=ContentType.objects.get_for_model(model)).order_by("action_time")

    def test_a_provider_switch_is_recorded_with_field_names_only(self):
        self.make_graph()

        self.client.post(self.edit_url, self.post_data("graph"))

        (entry,) = self.entries(EmailServiceConfig)
        self.assertEqual(
            (entry.user_id, entry.action_flag, entry.object_id), (self.admin_user.pk, CHANGE, str(self.config.pk))
        )
        message = entry.get_change_message()
        for label in ("Config Name", "Provider", "From Email", "From Name"):
            self.assertIn(label, message)
        for value in ("graph", "updated@example.com", "Updated Sender"):
            self.assertNotIn(value, entry.change_message)
        self.assertFalse(self.entries(MicrosoftGraphProviderConfig).exists())

    def test_secret_fields_are_named_but_their_values_never_written(self):
        data = self.post_data("smtp") | {"aws-secret_access_key": "new-aws-secret", "smtp-password": "new-smtp-pass"}

        self.client.post(self.edit_url, data)

        aws_entry = self.entries(AWSCredentialConfig).get()
        smtp_entry = self.entries(SMTPProviderConfig).get()
        self.assertIn("Secret Access Key", aws_entry.get_change_message())
        self.assertIn("SMTP Password", smtp_entry.get_change_message())
        for entry in (aws_entry, smtp_entry):
            for secret in ("new-aws-secret", "new-smtp-pass", "test-secret", "existing-secret"):
                self.assertNotIn(secret, entry.change_message)

    def test_unchanged_rows_and_rejected_saves_leave_no_history(self):
        self.client.post(self.edit_url, self.post_data("ses"))
        self.assertEqual(self.entries(AWSCredentialConfig).count(), 0)
        count = LogEntry.objects.count()

        self.client.post(self.edit_url, self.post_data("ses"))  # the same values again
        self.client.post(self.edit_url, self.post_data("graph", **{"email-name": "Rejected"}))  # no Graph config

        self.assertEqual(LogEntry.objects.count(), count)

    def test_a_first_email_config_is_recorded_as_added(self):
        EmailServiceConfig.objects.all().delete()

        self.client.post(self.edit_url, self.post_data("ses"))

        (entry,) = self.entries(EmailServiceConfig)
        self.assertEqual(entry.action_flag, ADDITION)
