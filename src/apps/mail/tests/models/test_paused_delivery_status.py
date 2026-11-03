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

    def test_0020_follows_0019_and_mail_keeps_one_leaf(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        node = ("mail", "0020_paused_delivery_status")

        mail_leaves = [leaf for leaf in loader.graph.leaf_nodes() if leaf[0] == "mail"]
        self.assertEqual(len(mail_leaves), 1)
        # Later mail migrations (0021 Manual Emails help text, ...) build on 0020.
        self.assertIn(node, loader.graph.forwards_plan(mail_leaves[0]))
        parents = {parent.key for parent in loader.graph.node_map[node].parents}
        self.assertEqual(parents, {("mail", "0019_carry_primary_opt_out_to_all_addresses")})
