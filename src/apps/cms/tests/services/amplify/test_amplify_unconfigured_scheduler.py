from django.test import TestCase, override_settings

from apps.cms.services.amplify import (
    AMPLIFY_REDIRECT_JOB_KIND,
    schedule_amplify_redirect_sync,
)
from apps.core.models import BackgroundJob


@override_settings(AMPLIFY_APP_ID="", BACKGROUND_JOBS_ENABLED=True)
class AmplifyUnconfiguredSchedulerTests(TestCase):
    def test_missing_app_id_leaves_redirect_pending_without_a_job(self):
        self.assertIsNone(schedule_amplify_redirect_sync(immediate=True))
        self.assertFalse(BackgroundJob.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND).exists())
