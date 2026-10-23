import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.authn.models import Member
from apps.cms.admin.layout.style_sheet import SEED_STATUS_NOTE, StyleSheetAdmin
from apps.cms.models import StyleSheet
from apps.cms.services.styles.drift import (
    STATUS_BACKUP_COPY,
    STATUS_EDITED,
    STATUS_IN_SYNC,
    STATUS_LABELS,
    STATUS_SETTINGS_CHANGED,
    STATUS_UNKNOWN,
    STATUS_UNMANAGED,
)
from apps.cms.views.layout import LAYOUT_CACHE_KEY, LAYOUT_STYLESHEET_CACHE_KEY


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

    def test_import_get_renders_upload_form(self):
        response = self.client.get(reverse("admin:cms_stylesheet_import"))
        self.assertEqual(response.status_code, 200)
        # No results have been computed on a GET.
        self.assertNotIn("has_results", response.context or {})

    def test_import_without_file_shows_error(self):
        response = self.client.post(reverse("admin:cms_stylesheet_import"), {"action": "dry_run"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Please select a JSON file to import.", response.content.decode())

    def test_import_invalid_json_shows_error(self):
        upload = SimpleUploadedFile("bad.json", b"{not valid json", content_type="application/json")
        response = self.client.post(
            reverse("admin:cms_stylesheet_import"),
            {"json_file": upload, "action": "dry_run"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Invalid JSON file:", response.content.decode())

    def test_import_row_not_object_reports_error(self):
        # Entry is a string, not an object -> normalize_stylesheet_row error path.
        upload = SimpleUploadedFile(
            "stylesheets.json",
            json.dumps({"version": 1, "stylesheets": ["not-an-object"]}).encode("utf-8"),
            content_type="application/json",
        )
        response = self.client.post(
            reverse("admin:cms_stylesheet_import"),
            {"json_file": upload, "action": "dry_run"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("expected an object", response.content.decode())
        self.assertEqual(StyleSheet.objects.count(), 0)

    def test_import_row_validation_error_reported(self):
        # Missing required name triggers full_clean ValidationError -> error row surfaced.
        response = self._upload(
            [{"name": "", "display_name": "No Name", "css": "/* x */"}],
            action="execute",
        )
        self.assertEqual(response.status_code, 200)
        # Execution is blocked because validation errors exist.
        self.assertIn("Import not executed because validation errors were found.", response.content.decode())
        self.assertEqual(StyleSheet.objects.count(), 0)


class StyleSheetAdminSaveModelTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin_user = Member.objects.create_superuser(
            password="testpass123",
            first_name="Save",
            last_name="Admin",
        )
        self.client.force_login(self.admin_user)
        StyleSheet.objects.all().delete()

    def tearDown(self):
        cache.clear()

    def test_save_model_busts_layout_cache(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from apps.cms.admin.layout.style_sheet import StyleSheetAdmin

        cache.set("layout:data", {"stale": True}, timeout=60)
        admin_obj = StyleSheetAdmin(StyleSheet, AdminSite())
        request = RequestFactory().post("/admin/cms/stylesheet/add/")
        request.user = self.admin_user
        sheet = StyleSheet(name="fresh", display_name="Fresh", css="/* fresh */", sort_order=1)

        admin_obj.save_model(request, sheet, form=None, change=False)

        self.assertTrue(StyleSheet.objects.filter(name="fresh").exists())
        self.assertIsNone(cache.get("layout:data"))


SEED_SITE = {"name": "site", "display_name": "Site", "description": "", "css": "body {\n  color: #333;\n}\n"}
SEED_HOME = {"name": "home", "display_name": "Home", "description": "", "css": ".home-hero {\n  margin: 0;\n}\n"}


class StyleSheetAdminSeedStatusTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin_user = Member.objects.create_superuser(
            password="testpass123",
            first_name="Seed",
            last_name="Admin",
        )
        self.client.force_login(self.admin_user)
        StyleSheet.objects.all().delete()
        # Every repo seed sheet is retired, so the labels are checked against a seed of live sheets.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        seed_path = Path(tmp.name) / "stylesheets.json"
        seed_path.write_text(
            json.dumps(
                [
                    {"model": "cms.stylesheet", "pk": 1, "fields": {**SEED_SITE, "is_active": True, "sort_order": 10}},
                    {"model": "cms.stylesheet", "pk": 2, "fields": {**SEED_HOME, "is_active": True, "sort_order": 100}},
                ]
            ),
            encoding="utf-8",
        )
        patcher = patch("apps.cms.services.styles.drift.SEED_PATH", seed_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        StyleSheet.objects.create(
            name="site",
            display_name="Seeded Global Row",
            css=SEED_SITE["css"].replace("\n", "\r\n"),
            sort_order=10,
        )
        StyleSheet.objects.create(
            name="home",
            display_name="Edited Home Row",
            css=SEED_HOME["css"] + "\n.extra { color: red; }\n",
            sort_order=100,
        )
        StyleSheet.objects.create(name="custom", display_name="Custom Unmanaged Row", css=".x {}", sort_order=200)

    def tearDown(self):
        cache.clear()

    def _row(self, content, display_name):
        """The changelist ``<tr>`` that holds ``display_name``."""
        rows = [row for row in content.split("<tr") if display_name in row]
        self.assertEqual(len(rows), 1, f"expected one row for {display_name!r}")
        return rows[0]

    def test_changelist_shows_repo_seed_column_with_status_labels(self):
        response = self.client.get(reverse("admin:cms_stylesheet_changelist"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("column-seed_status", content)
        for display_name, status in (
            ("Seeded Global Row", STATUS_IN_SYNC),
            ("Edited Home Row", STATUS_EDITED),
            ("Custom Unmanaged Row", STATUS_UNMANAGED),
        ):
            with self.subTest(row=display_name):
                cell = f'data-label="Repo seed">{STATUS_LABELS[status]}</td>'
                self.assertIn(cell, self._row(content, display_name))

    def test_changelist_renders_seed_note(self):
        response = self.client.get(reverse("admin:cms_stylesheet_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["seed_status_note"], SEED_STATUS_NOTE)
        content = response.content.decode()
        self.assertIn('data-role="stylesheet-seed-note"', content)
        note_start = content.index('data-role="stylesheet-seed-note"')
        self.assertIn("manage.py stylesheet_drift", content[note_start : content.index("</p>", note_start)])

    def test_seed_status_method_returns_label(self):
        from django.contrib.admin.sites import AdminSite

        model_admin = StyleSheetAdmin(StyleSheet, AdminSite())

        self.assertEqual(model_admin.seed_status(StyleSheet.objects.get(name="home")), STATUS_LABELS[STATUS_EDITED])
        backup = StyleSheet(name="site-pre-redesign", css=".old {}", is_active=False)
        self.assertEqual(model_admin.seed_status(backup), STATUS_LABELS[STATUS_BACKUP_COPY])
        self.assertIn("seed_status", model_admin.list_display)

    def test_changelist_labels_settings_changes_and_active_backup_copies(self):
        StyleSheet.objects.filter(name="site").update(sort_order=11)
        StyleSheet.objects.create(
            name="site-pre-redesign", display_name="Switched Back Copy", css=".old {}", sort_order=5
        )
        StyleSheet.objects.create(
            name="home-pre-redesign",
            display_name="Inactive Backup Copy",
            css=".old {}",
            sort_order=6,
            is_active=False,
        )

        content = self.client.get(reverse("admin:cms_stylesheet_changelist")).content.decode()

        for display_name, status in (
            ("Seeded Global Row", STATUS_SETTINGS_CHANGED),
            ("Switched Back Copy", STATUS_UNMANAGED),
            ("Inactive Backup Copy", STATUS_BACKUP_COPY),
        ):
            with self.subTest(row=display_name):
                cell = f'data-label="Repo seed">{STATUS_LABELS[status]}</td>'
                self.assertIn(cell, self._row(content, display_name))

    def test_changelist_shows_unknown_when_the_seed_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "stylesheets.json"
            with patch("apps.cms.services.styles.drift.SEED_PATH", missing):
                response = self.client.get(reverse("admin:cms_stylesheet_changelist"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        cell = f'data-label="Repo seed">{STATUS_LABELS[STATUS_UNKNOWN]}</td>'
        for display_name in ("Seeded Global Row", "Edited Home Row", "Custom Unmanaged Row"):
            with self.subTest(row=display_name):
                self.assertIn(cell, self._row(content, display_name))
