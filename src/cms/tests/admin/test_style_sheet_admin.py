import json

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from authn.models import Member
from cms.models import StyleSheet
from cms.views.views import LAYOUT_CACHE_KEY, LAYOUT_STYLESHEET_CACHE_KEY


class StyleSheetAdminImportExportTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.admin_user = Member.objects.create_superuser(
            password="testpass123",
            first_name="Style",
            last_name="Admin",
        )
        self.client.force_login(self.admin_user)
        StyleSheet.objects.all().delete()

    def tearDown(self):
        cache.clear()

    # noinspection PyMethodMayBeStatic
    def _bundle(self, stylesheets):
        return json.dumps({"version": 1, "stylesheets": stylesheets}).encode("utf-8")

    def _upload(self, stylesheets, action="dry_run"):
        upload = SimpleUploadedFile("stylesheets.json", self._bundle(stylesheets), content_type="application/json")
        return self.client.post(
            reverse("admin:cms_stylesheet_import"),
            {"json_file": upload, "action": action},
        )

    def test_changelist_shows_import_export_buttons(self):
        response = self.client.get(reverse("admin:cms_stylesheet_changelist"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Export JSON", content)
        self.assertIn("Import JSON", content)
        self.assertIn(reverse("admin:cms_stylesheet_export"), content)
        self.assertIn(reverse("admin:cms_stylesheet_import"), content)

    def test_export_all_stylesheets_uses_importable_bundle_shape(self):
        StyleSheet.objects.create(name="z", display_name="Z", css="/* z */", sort_order=20)
        StyleSheet.objects.create(name="a", display_name="A", css="/* a */", sort_order=10, is_active=False)

        response = self.client.get(reverse("admin:cms_stylesheet_export"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("attachment", response["Content-Disposition"])

        bundle = json.loads(response.content)
        self.assertEqual(bundle["version"], 1)
        self.assertEqual([row["name"] for row in bundle["stylesheets"]], ["a", "z"])
        self.assertEqual(
            bundle["stylesheets"][0],
            {
                "name": "a",
                "display_name": "A",
                "description": "",
                "css": "/* a */",
                "is_active": False,
                "sort_order": 10,
            },
        )

    def test_import_dry_run_previews_full_sync_without_changes(self):
        StyleSheet.objects.create(name="existing", display_name="Existing", css="/* old */", sort_order=5)
        StyleSheet.objects.create(name="remove-me", display_name="Remove Me", css="/* remove */", sort_order=10)

        response = self._upload(
            [
                {
                    "name": "existing",
                    "display_name": "Existing Updated",
                    "description": "Updated description",
                    "css": "/* updated */",
                    "is_active": False,
                    "sort_order": 1,
                },
                {
                    "name": "new-sheet",
                    "display_name": "New Sheet",
                    "description": "",
                    "css": "/* new */",
                    "is_active": True,
                    "sort_order": 2,
                },
            ],
            action="dry_run",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StyleSheet.objects.count(), 2)
        self.assertTrue(StyleSheet.objects.filter(name="remove-me").exists())
        existing = StyleSheet.objects.get(name="existing")
        self.assertEqual(existing.display_name, "Existing")
        self.assertEqual(existing.css, "/* old */")
        content = response.content.decode()
        self.assertIn("Import Preview (Dry Run)", content)
        self.assertIn("DELETE", content)
        self.assertIn("Ready", content)

    def test_import_execute_full_sync_creates_updates_and_deletes(self):
        StyleSheet.objects.create(
            name="existing",
            display_name="Existing",
            description="Old description",
            css="/* old */",
            is_active=True,
            sort_order=5,
        )
        StyleSheet.objects.create(name="remove-me", display_name="Remove Me", css="/* remove */", sort_order=10)
        cache.set(LAYOUT_CACHE_KEY, {"stale": True}, timeout=60)
        cache.set(LAYOUT_STYLESHEET_CACHE_KEY, "stale css", timeout=60)

        with self.captureOnCommitCallbacks(execute=True):
            response = self._upload(
                [
                    {
                        "name": "existing",
                        "display_name": "Existing Updated",
                        "description": "Updated description",
                        "css": "/* updated */",
                        "is_active": False,
                        "sort_order": 1,
                    },
                    {
                        "name": "new-sheet",
                        "display_name": "New Sheet",
                        "description": "",
                        "css": "/* new */",
                        "is_active": True,
                        "sort_order": 2,
                    },
                ],
                action="execute",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(StyleSheet.objects.order_by("sort_order", "name").values_list("name", flat=True)),
            ["existing", "new-sheet"],
        )

        existing = StyleSheet.objects.get(name="existing")
        self.assertEqual(existing.display_name, "Existing Updated")
        self.assertEqual(existing.description, "Updated description")
        self.assertEqual(existing.css, "/* updated */")
        self.assertFalse(existing.is_active)
        self.assertEqual(existing.sort_order, 1)
        self.assertFalse(StyleSheet.objects.filter(name="remove-me").exists())
        self.assertIsNone(cache.get(LAYOUT_CACHE_KEY))
        self.assertIsNone(cache.get(LAYOUT_STYLESHEET_CACHE_KEY))

        content = response.content.decode()
        self.assertIn("Import Results", content)
        self.assertIn("OK", content)

    def test_import_invalid_bundle_does_not_change_database(self):
        StyleSheet.objects.create(name="existing", display_name="Existing", css="/* old */", sort_order=5)
        upload = SimpleUploadedFile(
            "stylesheets.json",
            json.dumps({"pages": []}).encode("utf-8"),
            content_type="application/json",
        )

        response = self.client.post(
            reverse("admin:cms_stylesheet_import"),
            {"json_file": upload, "action": "execute"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(StyleSheet.objects.count(), 1)
        self.assertIn("expected a JSON object with a", response.content.decode())
        self.assertIn("stylesheets", response.content.decode())

    def test_import_duplicate_names_is_blocked(self):
        response = self._upload(
            [
                {
                    "name": "dup",
                    "display_name": "First",
                    "description": "",
                    "css": "/* one */",
                    "is_active": True,
                    "sort_order": 1,
                },
                {
                    "name": "dup",
                    "display_name": "Second",
                    "description": "",
                    "css": "/* two */",
                    "is_active": True,
                    "sort_order": 2,
                },
            ],
            action="execute",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(StyleSheet.objects.filter(name="dup").exists())
        self.assertIn("Duplicate stylesheet name", response.content.decode())
