from apps.cms.models import CMSEmbedWidget, CMSPage
from apps.cms.tests.cms.import_export.test_cms_import import _CMSImportCase


class CMSImportTest(_CMSImportCase):
    def test_import_persists_block_level_schedule_id(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.event.models import CurrentProjectSchedule

        CMSEmbedWidget.objects.create(widget_type="app_route", app_route="/schedule", slug="schedule-embed")
        schedule = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        bundle = self._make_bundle(
            [
                {
                    "slug": "embed-import-schedule",
                    "route": "/embed-import-schedule",
                    "title": "Embed Import Schedule",
                    "blocks": [
                        {
                            "block_type": "embed_widget",
                            "sort_order": 0,
                            "data": {"slug": "schedule-embed", "schedule_id": str(schedule.pk)},
                        }
                    ],
                }
            ]
        )
        f = SimpleUploadedFile("import.json", bundle, content_type="application/json")

        response = self.client.post(
            "/admin/cms/cmspage/import/",
            {"json_file": f, "action": "execute"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        block = CMSPage.objects.get(slug="embed-import-schedule").blocks.get()
        self.assertEqual(block.data["schedule_id"], str(schedule.pk))

    def test_import_rejects_block_level_schedule_id_that_does_not_exist_here(self):
        # Schedule ids are environment-specific; a bundle exported elsewhere
        # must fail loudly instead of silently storing a dangling reference.
        from django.core.files.uploadedfile import SimpleUploadedFile

        CMSEmbedWidget.objects.create(widget_type="app_route", app_route="/schedule", slug="schedule-embed")
        bundle = self._make_bundle(
            [
                {
                    "slug": "embed-import-missing-schedule",
                    "route": "/embed-import-missing-schedule",
                    "title": "Embed Import Missing Schedule",
                    "blocks": [
                        {
                            "block_type": "embed_widget",
                            "sort_order": 0,
                            "data": {
                                "slug": "schedule-embed",
                                "schedule_id": "00000000-0000-0000-0000-000000000000",
                            },
                        }
                    ],
                }
            ]
        )
        f = SimpleUploadedFile("import.json", bundle, content_type="application/json")

        response = self.client.post(
            "/admin/cms/cmspage/import/",
            {"json_file": f, "action": "execute"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CMSPage.objects.filter(slug="embed-import-missing-schedule").exists())
        self.assertIn("No schedule found", response.content.decode())

    def test_import_dry_run_no_changes(self):
        """Dry run returns results but creates nothing."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        bundle = self._make_bundle(
            [
                {
                    "slug": "dry-run",
                    "route": "/dry-run",
                    "title": "Dry Run",
                    "blocks": [],
                }
            ]
        )
        f = SimpleUploadedFile("import.json", bundle, content_type="application/json")

        response = self.client.post(
            "/admin/cms/cmspage/import/",
            {"json_file": f, "action": "dry_run"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CMSPage.objects.filter(slug="dry-run").exists())
