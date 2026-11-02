"""Campaign recipients a delivery limit held back can be marked "paused" (migration 0020)."""

from django.core.exceptions import ValidationError
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase

from apps.mail.models import RecipientLog, SmsRecipientLog

PAUSED = ("paused", "Paused by delivery limits")


class PausedDeliveryStatusTests(SimpleTestCase):
    def test_email_and_sms_recipients_accept_the_paused_status(self):
        for model in (RecipientLog, SmsRecipientLog):
            with self.subTest(model=model.__name__):
                field = model._meta.get_field("status")
                self.assertIn(PAUSED, field.choices)
                self.assertEqual(field.clean("paused", None), "paused")
                self.assertEqual(field.default, "pending")
                with self.assertRaises(ValidationError):
                    field.clean("held", None)

    def test_0020_follows_0019_and_is_the_mail_leaf(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        node = ("mail", "0020_paused_delivery_status")

        self.assertEqual([leaf for leaf in loader.graph.leaf_nodes() if leaf[0] == "mail"], [node])
        parents = {parent.key for parent in loader.graph.node_map[node].parents}
        self.assertEqual(parents, {("mail", "0019_carry_primary_opt_out_to_all_addresses")})
