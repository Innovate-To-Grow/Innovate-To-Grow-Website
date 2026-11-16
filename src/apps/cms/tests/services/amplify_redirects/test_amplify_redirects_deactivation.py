from unittest.mock import patch

from django.test import override_settings

from apps.cms.models import RouteRedirect
from apps.cms.tests.services.amplify_redirects.test_amplify_redirects import _AmplifyRedirectJobCase


@override_settings(AMPLIFY_APP_ID="app-123", BACKGROUND_JOBS_ENABLED=True)
class AmplifyRedirectJobTests(_AmplifyRedirectJobCase):
    @patch("apps.cms.services.amplify.jobs.schedule_amplify_redirect_sync")
    def test_deactivation_schedules_followup_even_before_ownership_is_confirmed(self, schedule):
        redirect = RouteRedirect.objects.create(
            source_path="/in-flight-deactivation",
            destination_path="/job-target",
            is_active=True,
        )
        self.assertFalse(redirect.edge_rule_managed)
        redirect.is_active = False

        with self.captureOnCommitCallbacks(execute=True):
            redirect.save(update_fields=["is_active", "updated_at"])

        redirect.refresh_from_db()
        self.assertEqual(redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)
        schedule.assert_called_once_with(redirect_ids=(redirect.pk,))
