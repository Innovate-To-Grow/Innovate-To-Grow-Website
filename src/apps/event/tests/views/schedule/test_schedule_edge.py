from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.event.models import CurrentProjectSchedule
from apps.event.services import sync_schedule
from apps.event.tests.helpers import sample_projects_records, sample_tracks_records


class CurrentEventScheduleViewEdgeTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_invalid_schedule_id_returns_404(self):
        # A non-UUID schedule_id triggers the ValueError/ValidationError handler in _get_config
        # which returns None, so the view responds 404.
        response = self.client.get("/event/schedule/", {"schedule_id": "not-a-uuid"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"], "No schedule configured.")

    def test_config_disappears_between_lookup_and_refetch_returns_404(self):
        config = CurrentProjectSchedule.objects.create(name="Race Day")
        sync_schedule(config, tracks_records=sample_tracks_records(), projects_records=sample_projects_records())

        # load() returns a stale config, but the prefetch re-fetch (the only
        # filter() call left) yields None -> the view's `config is None` guard fires.
        empty_query = MagicMock()
        empty_query.prefetch_related.return_value.first.return_value = None

        with patch.object(CurrentProjectSchedule.objects, "filter", return_value=empty_query):
            with patch.object(CurrentProjectSchedule, "load", return_value=config):
                response = self.client.get("/event/schedule/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["detail"], "No schedule configured.")
