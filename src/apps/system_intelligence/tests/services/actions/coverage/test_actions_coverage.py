"""Line-coverage tests for apps.system_intelligence.services.actions.

These exercise the helper, ORM-safety, comparison, cascade, context, and
approval code paths that the behavioural tests in this package do not reach.
"""

import json
from unittest.mock import patch

from django.test import TestCase

from apps.cms.models import NewsFeedSource
from apps.cms.models.content.news.sync_log import NewsSyncLog
from apps.event.tests.helpers import make_admin
from apps.system_intelligence.services import actions
from apps.system_intelligence.services.actions.engine.exceptions import ActionRequestError


# ---------------------------------------------------------------------------
# records/__init__.py
# ---------------------------------------------------------------------------
class RecordsReadToolTests(TestCase):
    def setUp(self):
        user = make_admin()
        tokens = actions.set_action_context(None, str(user.pk))
        self.addCleanup(actions.reset_action_context, tokens)

    def test_list_database_models_includes_allowed_excludes_denied(self):
        # The full model list exceeds the truncation limit, so assert on the
        # rendered text rather than re-parsing the (truncated) JSON.
        result = actions.list_database_models()
        self.assertIn('"label": "cms.NewsFeedSource"', result)
        # A readable, writable model carries the writable flag.
        self.assertIn('"writable": true', result)
        # A denied model (CMSPage) must never be listed.
        self.assertNotIn('"label": "cms.CMSPage"', result)

    def test_list_database_models_sorted_by_label(self):
        # Patch get_models with a small, denial-free set so the JSON is not
        # truncated and ordering can be asserted exactly.
        models_in = [NewsSyncLog, NewsFeedSource]
        with patch(
            "apps.system_intelligence.services.actions.db.records.apps.get_models",
            return_value=models_in,
        ):
            result = actions.list_database_models()
        rows = json.loads(result)
        self.assertEqual([row["label"] for row in rows], ["cms.NewsFeedSource", "cms.NewsSyncLog"])

    def test_get_model_schema_lists_readable_and_writable_fields(self):
        result = actions.get_model_schema("cms", "NewsFeedSource")
        payload = json.loads(result)
        self.assertEqual(payload["model"], "cms.NewsFeedSource")
        self.assertEqual(payload["primary_key"], "id")
        readable = {f["name"] for f in payload["readable_fields"]}
        writable = {f["name"] for f in payload["writable_fields"]}
        self.assertIn("name", readable)
        self.assertIn("name", writable)
        # The UUID primary key is readable but not writable.
        self.assertIn("id", readable)
        self.assertNotIn("id", writable)

    def test_get_record_returns_safe_snapshot(self):
        source = NewsFeedSource.objects.create(
            name="UC Merced", source_key="ucm", feed_url="https://example.com/feed.xml"
        )
        result = actions.get_record("cms", "NewsFeedSource", str(source.pk))
        payload = json.loads(result)
        self.assertEqual(payload["name"], "UC Merced")
        self.assertEqual(payload["__repr__"], "UC Merced")

    def test_search_records_filters_orders_and_limits(self):
        NewsFeedSource.objects.create(name="Alpha", source_key="a", feed_url="https://example.com/a.xml")
        NewsFeedSource.objects.create(name="Beta", source_key="b", feed_url="https://example.com/b.xml")
        NewsFeedSource.objects.create(name="Gamma", source_key="g", feed_url="https://example.com/g.xml")
        result = actions.search_records(
            "cms",
            "NewsFeedSource",
            filters={"name__icontains": "a"},
            ordering="-name",
            fields=["name", "source_key"],
            limit=2,
        )
        payload = json.loads(result)
        self.assertEqual(payload["model"], "cms.NewsFeedSource")
        self.assertEqual(payload["shown"], 2)
        self.assertEqual(payload["total"], 3)
        # Ordering by -name then limited to 2 rows.
        self.assertEqual([row["name"] for row in payload["rows"]], ["Gamma", "Beta"])
        # Only the selected fields are present.
        self.assertEqual(set(payload["rows"][0]), {"name", "source_key"})

    def test_search_records_defaults_fields_when_none(self):
        NewsFeedSource.objects.create(name="Solo", source_key="solo", feed_url="https://example.com/s.xml")
        result = actions.search_records("cms", "NewsFeedSource")
        payload = json.loads(result)
        self.assertEqual(payload["shown"], 1)
        self.assertIn("name", payload["rows"][0])

    def test_search_records_rejects_non_dict_filters(self):
        with self.assertRaises(ActionRequestError) as cm:
            actions.search_records("cms", "NewsFeedSource", filters=["not", "a", "dict"])
        self.assertIn("filters must be an object", str(cm.exception))
