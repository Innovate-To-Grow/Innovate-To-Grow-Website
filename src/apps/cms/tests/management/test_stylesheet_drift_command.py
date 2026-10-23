"""Tests for the ``stylesheet_drift`` management command."""

import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command, load_command_class
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.cms.models import CMSPage, StyleSheet
from apps.cms.services.styles.drift import RETIRED_SHEETS, SEED_PATH, load_seed_sheets

DRIFT_HINT = "Port the wanted changes into the repo (or restore deleted sheets) before a migration re-syncs them."


def seed_record(pk, name, css, *, sort_order=10, is_active=True):
    return {
        "model": "cms.stylesheet",
        "pk": pk,
        "fields": {
            "name": name,
            "display_name": name.title(),
            "description": "",
            "css": css,
            "is_active": is_active,
            "sort_order": sort_order,
        },
    }


class StylesheetDriftCommandTests(TestCase):
    def setUp(self):
        cache.clear()
        StyleSheet.objects.all().delete()
        CMSPage.objects.all().delete()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        # gamma is inactive in the seed: it is listed as missing, but deleting it changes nothing a
        # re-sync would serve, so it is not drift (an active seed sheet that is deleted is).
        self.seed_path = self._write_seed(
            "seed.json",
            [
                seed_record(1, "alpha", "a {}\n", sort_order=10),
                seed_record(2, "beta", "b {}\nc {}\n", sort_order=20),
                seed_record(3, "gamma", "g {}\n", sort_order=30, is_active=False),
            ],
        )

    def _write_seed(self, filename, records):
        path = self.tmp / filename
        path.write_text(json.dumps(records), encoding="utf-8")
        return path

    def _run(self, *args, **options):
        out, err = StringIO(), StringIO()
        call_command("stylesheet_drift", *args, stdout=out, stderr=err, **options)
        return out.getvalue(), err.getvalue()

    def _run_failing(self, *args, **options):
        out, err = StringIO(), StringIO()
        with self.assertRaises(CommandError) as caught:
            call_command("stylesheet_drift", *args, stdout=out, stderr=err, **options)
        return out.getvalue(), err.getvalue(), caught.exception

    def _create_in_sync_sheets(self):
        StyleSheet.objects.create(name="alpha", display_name="Alpha", css="a {}\r\n", sort_order=10)
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}\nc {}\n", sort_order=20)

    def test_active_edited_sheet_exits_with_status_1(self):
        StyleSheet.objects.create(name="alpha", display_name="Alpha", css="a {}\n", sort_order=10)
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}\nC {}\nd {}\n", sort_order=20)

        out, _err, error = self._run_failing(seed=str(self.seed_path))

        self.assertEqual(error.returncode, 1)
        self.assertEqual(str(error), f"1 sheet(s) differ from the repo seed: beta. {DRIFT_HINT}")
        lines = out.splitlines()
        self.assertEqual(lines[0], f"Seed: {self.seed_path}")
        self.assertRegex(lines[1], r"^status\s+on\s+name\s+changes\s+settings$")
        self.assertRegex(out, r"(?m)^in_sync\s+on\s+alpha$")
        self.assertRegex(out, r"(?m)^edited\s+on\s+beta\s+\+2/-1$")
        self.assertRegex(out, r"missing\s+gamma\s+\(in seed only\)")
        self.assertNotIn("--- seed/", out)

    def test_active_unmanaged_sheets_exit_with_status_1(self):
        self._create_in_sync_sheets()
        StyleSheet.objects.create(name="custom", display_name="Custom", css="x {}", sort_order=40)
        StyleSheet.objects.create(name="extra", display_name="Extra", css="y {}", sort_order=50)

        out, _err, error = self._run_failing(seed=str(self.seed_path))

        self.assertEqual(str(error), f"2 sheet(s) differ from the repo seed: custom, extra. {DRIFT_HINT}")
        self.assertRegex(out, r"(?m)^unmanaged\s+on\s+custom$")
        self.assertRegex(out, r"(?m)^unmanaged\s+on\s+extra$")

    def test_active_backup_copy_is_unmanaged_and_fails(self):
        self._create_in_sync_sheets()
        StyleSheet.objects.create(name="beta-pre-redesign", display_name="Beta old", css="old {}", sort_order=21)

        out, _err, error = self._run_failing(seed=str(self.seed_path))

        self.assertEqual(str(error), f"1 sheet(s) differ from the repo seed: beta-pre-redesign. {DRIFT_HINT}")
        self.assertRegex(out, r"(?m)^unmanaged\s+on\s+beta-pre-redesign$")
        self.assertNotIn("backup_copy", out)

    def test_only_inactive_rows_nobody_serves_succeeds(self):
        seed_path = self._write_seed(
            "with-inactive.json",
            [
                seed_record(1, "alpha", "a {}\n", sort_order=10),
                seed_record(2, "beta", "b {}\nc {}\n", sort_order=20),
                seed_record(4, "delta", "d {}\n", sort_order=40, is_active=False),
            ],
        )
        self._create_in_sync_sheets()
        # Inactive in the seed as well, so a re-sync would not switch it on.
        StyleSheet.objects.create(
            name="delta", display_name="Delta", css="d { color: red; }", sort_order=40, is_active=False
        )
        StyleSheet.objects.create(name="custom", display_name="Custom", css="x {}", is_active=False)
        StyleSheet.objects.create(name="beta-pre-redesign", display_name="Beta old", css="old {}", is_active=False)

        out, err = self._run(seed=str(seed_path))

        self.assertRegex(out, r"(?m)^edited\s+off\s+delta\s+\+1/-1$")
        self.assertRegex(out, r"(?m)^unmanaged\s+off\s+custom$")
        self.assertRegex(out, r"(?m)^backup_copy\s+off\s+beta-pre-redesign$")
        self.assertRegex(out, r"(?m)^in_sync\s+on\s+alpha$")
        self.assertRegex(out, r"(?m)^in_sync\s+on\s+beta$")
        self.assertEqual(err, "")

    def test_deactivated_seed_sheet_fails_and_shows_the_setting(self):
        StyleSheet.objects.create(name="alpha", display_name="Alpha", css="a {}\n", sort_order=10, is_active=False)
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}\nc {}\n", sort_order=20)

        out, _err, error = self._run_failing(seed=str(self.seed_path))

        self.assertEqual(str(error), f"1 sheet(s) differ from the repo seed: alpha. {DRIFT_HINT}")
        self.assertRegex(out, r"(?m)^settings_changed\s+off\s+alpha\s+is_active$")

    def test_reordered_seed_sheet_fails_and_shows_the_setting(self):
        StyleSheet.objects.create(name="alpha", display_name="Alpha", css="a {}\n", sort_order=10)
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}\nc {}\n", sort_order=25)

        out, _err, error = self._run_failing(seed=str(self.seed_path))

        self.assertIn("1 sheet(s) differ from the repo seed: beta.", str(error))
        self.assertRegex(out, r"(?m)^settings_changed\s+on\s+beta\s+sort_order$")

    def test_settings_column_lists_every_changed_setting_next_to_the_line_counts(self):
        StyleSheet.objects.create(name="alpha", display_name="Alpha", css="a {}\n", sort_order=11, is_active=False)
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}\nC {}\n", sort_order=25)

        out, _err, error = self._run_failing(seed=str(self.seed_path))

        self.assertRegex(out, r"(?m)^settings_changed\s+off\s+alpha\s+is_active, sort_order$")
        self.assertRegex(out, r"(?m)^edited\s+on\s+beta\s+\+1/-1  sort_order$")
        self.assertIn("2 sheet(s) differ from the repo seed: alpha, beta.", str(error))

    def test_deleted_active_seed_sheet_exits_with_status_1_and_names_it(self):
        StyleSheet.objects.create(name="alpha", display_name="Alpha", css="a {}\n", sort_order=10)

        out, _err, error = self._run_failing(seed=str(self.seed_path))

        self.assertEqual(error.returncode, 1)
        self.assertEqual(str(error), f"1 sheet(s) differ from the repo seed: beta (deleted). {DRIFT_HINT}")
        self.assertRegex(out, r"(?m)^in_sync\s+on\s+alpha$")
        self.assertRegex(out, r"(?m)^missing\s+beta\s+\(in seed only\)$")
        self.assertRegex(out, r"(?m)^missing\s+gamma\s+\(in seed only\)$")

    def test_deleted_sheets_are_named_after_the_drifted_rows(self):
        StyleSheet.objects.create(name="gamma", display_name="Gamma", css="g {}\n", sort_order=30)

        _out, _err, error = self._run_failing(seed=str(self.seed_path))

        # gamma was switched on (is_active differs from the seed); alpha and beta were deleted.
        self.assertEqual(
            str(error), f"3 sheet(s) differ from the repo seed: gamma, alpha (deleted), beta (deleted). {DRIFT_HINT}"
        )

    def test_json_option_lists_deleted_active_seed_sheets(self):
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}\nc {}\n", sort_order=20)

        out, _err, error = self._run_failing("--json", seed=str(self.seed_path))

        report = json.loads(out)
        self.assertEqual(report["missing_from_database"], ["alpha", "gamma"])
        self.assertEqual(report["deleted_active_seed_sheets"], ["alpha"])
        self.assertIn("1 sheet(s) differ from the repo seed: alpha (deleted).", str(error))

    def test_missing_seed_file_is_an_error(self):
        self._create_in_sync_sheets()
        missing = self.tmp / "no-such-seed.json"
        export_path = self.tmp / "backup.json"

        out, err, error = self._run_failing(export=str(export_path), seed=str(missing))

        self.assertEqual(str(error), f"Seed file not found: {missing}")
        self.assertEqual(error.returncode, 1)
        self.assertEqual((out, err), ("", ""))
        self.assertFalse(export_path.exists())

    def test_missing_seed_file_is_an_error_in_json_mode(self):
        missing = self.tmp / "no-such-seed.json"

        out, _err, error = self._run_failing("--json", seed=str(missing))

        self.assertEqual(str(error), f"Seed file not found: {missing}")
        self.assertEqual(out, "")

    def test_table_lists_pages_with_page_css(self):
        self._create_in_sync_sheets()
        CMSPage.objects.create(slug="styled", route="/styled", title="Styled", page_css=".s {}", status="published")
        CMSPage.objects.create(slug="plain", route="/plain", title="Plain")

        out, _err = self._run(seed=str(self.seed_path))

        self.assertIn("Pages with page_css: 1", out)
        self.assertIn("  /styled (published, 5 chars)", out)
        self.assertNotIn("/plain", out)

    def test_diff_option_prints_the_unified_diff(self):
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}\nC {}\n", sort_order=20)

        out, _err, _error = self._run_failing("--diff", seed=str(self.seed_path))

        self.assertIn("--- seed/beta.css\n+++ database/beta.css\n", out)
        self.assertIn("\n-c {}\n", out)
        self.assertIn("\n+C {}\n", out)

    def test_diff_option_without_edits_prints_no_diff(self):
        self._create_in_sync_sheets()
        out, _err = self._run("--diff", seed=str(self.seed_path))
        self.assertNotIn("--- seed/", out)

    def test_json_option_prints_the_report(self):
        self._create_in_sync_sheets()

        out, _err = self._run("--json", seed=str(self.seed_path))

        report = json.loads(out)
        self.assertEqual(report["seed_path"], str(self.seed_path))
        self.assertTrue(report["seed_found"])
        self.assertEqual([entry["name"] for entry in report["sheets"]], ["alpha", "beta"])
        self.assertEqual([entry["changed_settings"] for entry in report["sheets"]], [[], []])
        self.assertEqual(report["counts"], {"in_sync": 2})
        self.assertEqual(report["missing_from_database"], ["gamma"])
        self.assertEqual(report["deleted_active_seed_sheets"], [])
        self.assertEqual(report["pages_with_css"], [])

    def test_json_option_includes_changed_settings(self):
        StyleSheet.objects.create(name="alpha", display_name="Alpha", css="a {}\n", sort_order=12, is_active=False)
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}\nc {}\n", sort_order=20)

        out, _err, error = self._run_failing("--json", seed=str(self.seed_path))

        entries = {entry["name"]: entry for entry in json.loads(out)["sheets"]}
        self.assertEqual(entries["alpha"]["status"], "settings_changed")
        self.assertEqual(entries["alpha"]["changed_settings"], ["is_active", "sort_order"])
        self.assertEqual((entries["beta"]["status"], entries["beta"]["changed_settings"]), ("in_sync", []))
        self.assertIn("1 sheet(s) differ from the repo seed: alpha.", str(error))

    def test_json_option_still_fails_on_drift(self):
        StyleSheet.objects.create(name="beta", display_name="Beta", css="changed {}", sort_order=20)

        out, _err, _error = self._run_failing("--json", seed=str(self.seed_path))

        report = json.loads(out)
        self.assertEqual(report["sheets"][0]["status"], "edited")
        self.assertIn("+changed {}", report["sheets"][0]["diff"])

    def test_export_option_writes_sheets_and_page_css(self):
        self._create_in_sync_sheets()
        CMSPage.objects.create(slug="styled", route="/styled", title="Styled", page_css=".s {}")
        export_path = self.tmp / "backup.json"

        _out, err = self._run(export=str(export_path), seed=str(self.seed_path))

        self.assertIn(f"Exported 2 sheet(s) to {export_path}", err)
        bundle = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(bundle["version"], 1)
        self.assertEqual([sheet["name"] for sheet in bundle["stylesheets"]], ["alpha", "beta"])
        self.assertEqual(bundle["stylesheets"][0]["css"], "a {}\r\n")
        self.assertEqual(bundle["pages_with_css"], [{"slug": "styled", "route": "/styled", "page_css": ".s {}"}])

    def test_export_is_written_before_failing_on_drift(self):
        StyleSheet.objects.create(name="custom", display_name="Custom", css="x {}")
        export_path = self.tmp / "backup.json"

        self._run_failing(export=str(export_path), seed=str(self.seed_path))

        bundle = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual([sheet["name"] for sheet in bundle["stylesheets"]], ["custom"])

    def test_seed_option_is_honoured(self):
        self._create_in_sync_sheets()
        other_seed = self._write_seed("other.json", [seed_record(1, "alpha", "z {}\n")])

        self._run(seed=str(self.seed_path))
        out, _err, error = self._run_failing("--json", seed=str(other_seed))

        report = json.loads(out)
        self.assertEqual(report["seed_path"], str(other_seed))
        self.assertEqual(
            {entry["name"]: entry["status"] for entry in report["sheets"]},
            {"alpha": "edited", "beta": "unmanaged"},
        )
        self.assertIn("2 sheet(s) differ from the repo seed: alpha, beta.", str(error))

    def test_default_seed_is_the_repo_seed(self):
        # setUp deleted every sheet. Every repo seed sheet is retired, so none of them reads as deleted.
        out, _err = self._run("--json")

        report = json.loads(out)
        seeds = load_seed_sheets()
        self.assertTrue(seeds)
        self.assertEqual(set(seeds), set(RETIRED_SHEETS))
        self.assertEqual(report["seed_path"], str(SEED_PATH))
        self.assertTrue(report["seed_found"])
        self.assertEqual(report["missing_from_database"], list(seeds))
        self.assertEqual(report["deleted_active_seed_sheets"], [])


class StylesheetDriftCommandHelpTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_help_names_every_kind_of_drift_including_deleted_seed_sheets(self):
        parser = load_command_class("cms", "stylesheet_drift").create_parser("manage.py", "stylesheet_drift")
        # A wide terminal keeps argparse from breaking "re-sync" at its hyphen; compare as one line.
        with patch.dict(os.environ, {"COLUMNS": "1000"}):
            text = " ".join(parser.format_help().split())

        self.assertIn("Exits with status 1", text)
        self.assertIn("an active seed sheet that was deleted (a re-sync recreates it)", text)
        self.assertIn("a seed sheet whose active flag or order changed", text)
        self.assertIn("an active sheet whose CSS differs from the seed or is not in it", text)


class StylesheetDriftCommandRealSeedTests(TestCase):
    """The migrated test database holds the repo seed with the component sheets retired, so the command passes."""

    def setUp(self):
        cache.clear()

    def test_migrated_database_passes(self):
        out = StringIO()

        call_command("stylesheet_drift", stdout=out)

        seeds = load_seed_sheets()
        self.assertEqual(out.getvalue().count("in_sync "), len(seeds) - len(RETIRED_SHEETS))
        self.assertEqual(out.getvalue().count("retired "), len(RETIRED_SHEETS))
        self.assertNotIn("missing ", out.getvalue())
        self.assertNotIn("settings_changed", out.getvalue())
