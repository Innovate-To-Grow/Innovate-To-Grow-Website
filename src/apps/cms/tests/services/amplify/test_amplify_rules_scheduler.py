from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.cms.services.amplify import reconcile as amplify_reconcile

from .amplify_helpers import _base_rules


class AmplifyRuleMergeTests(SimpleTestCase):
    def test_admin_proxy_setting_adds_all_reserved_backend_routes(self):
        rules = _base_rules(proxy_admin_paths=True)

        self.assertEqual(
            [rule["source"] for rule in rules],
            [
                "/sitemap.xml",
                "/api/<*>",
                "/admin",
                "/admin/<*>",
                "/static/<*>",
                "/media/<*>",
                rules[-1]["source"],
            ],
        )
        self.assertEqual(rules[2]["target"], "https://api.example/admin/")
        self.assertEqual(rules[-1]["target"], "/index.html")

    def test_postgres_scheduler_uses_transaction_advisory_lock(self):
        database = MagicMock()
        database.vendor = "postgresql"
        cursor = database.cursor.return_value.__enter__.return_value

        with patch.object(amplify_reconcile, "connection", database):
            with amplify_reconcile._serialize_scheduling():
                pass

        cursor.execute.assert_called_once_with(
            "SELECT pg_advisory_xact_lock(%s)",
            [amplify_reconcile._AMPLIFY_SCHEDULE_LOCK_ID],
        )
