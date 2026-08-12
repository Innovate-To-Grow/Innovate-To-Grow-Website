from django.test import TestCase

from apps.projects.models import PastProjectsSheetConfig, PastProjectSyncLog


class PastProjectSyncLogModelTest(TestCase):
    def setUp(self):
        self.config = PastProjectsSheetConfig.objects.create(name="Prod")

    def test_str_format(self):
        log = PastProjectSyncLog.objects.create(
            config=self.config,
            sync_type=PastProjectSyncLog.SyncType.MANUAL,
            status=PastProjectSyncLog.Status.SUCCESS,
        )
        self.assertEqual(str(log), "Prod — Manual Pull — Success")

    def test_ordering_newest_first(self):
        older = PastProjectSyncLog.objects.create(
            config=self.config,
            sync_type=PastProjectSyncLog.SyncType.AUTO,
            status=PastProjectSyncLog.Status.SUCCESS,
        )
        newer = PastProjectSyncLog.objects.create(
            config=self.config,
            sync_type=PastProjectSyncLog.SyncType.MANUAL,
            status=PastProjectSyncLog.Status.FAILED,
        )
        self.assertEqual(list(PastProjectSyncLog.objects.all()), [newer, older])
