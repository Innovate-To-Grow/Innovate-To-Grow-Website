"""Tests for ``apps.cms.services.styles.drift`` (StyleSheet rows compared with the repo seed)."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.cms.models import CMSPage, StyleSheet
from apps.cms.services.styles.drift import (
    SEED_PATH,
    SEED_SETTINGS_FIELDS,
    STATUS_BACKUP_COPY,
    STATUS_EDITED,
    STATUS_IN_SYNC,
    STATUS_LABELS,
    STATUS_RETIRED,
    STATUS_SETTINGS_CHANGED,
    STATUS_UNKNOWN,
    STATUS_UNMANAGED,
    changed_settings,
    css_checksum,
    describe_sheet,
    drift_report,
    drifted_sheets,
    export_rows,
    has_drift,
    is_backup_copy,
    is_drifted,
    load_seed_sheets,
    normalize_css,
    pages_with_css,
    seed_status_label,
    sheet_diff,
    sheet_status,
)


def seed_record(pk, name, css, *, is_active=True, sort_order=10, display_name=None, description=""):
    return {
        "model": "cms.stylesheet",
        "pk": pk,
        "fields": {
            "name": name,
            "display_name": display_name or name.title(),
            "description": description,
            "css": css,
            "is_active": is_active,
            "sort_order": sort_order,
        },
    }


def write_seed(test_case, records):
    """Write ``records`` to a fresh temp dir (a new path per call, so the seed lru_cache never serves stale data)."""
    tmp = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp.cleanup)
    path = Path(tmp.name) / "stylesheets.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def missing_seed_path(test_case):
    tmp = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp.cleanup)
    return Path(tmp.name) / "missing.json"


class NormalizeCssTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_crlf_becomes_lf(self):
        self.assertEqual(normalize_css("a {}\r\nb {}\r\n"), "a {}\nb {}\n")

    def test_lone_cr_becomes_lf(self):
        self.assertEqual(normalize_css("a {}\rb {}"), "a {}\nb {}\n")

    def test_trailing_whitespace_is_stripped(self):
        self.assertEqual(normalize_css("a {}  \nb {}\t\n"), "a {}\nb {}\n")

    def test_trailing_blank_lines_collapse_to_one_newline(self):
        self.assertEqual(normalize_css("a {}\n\n\n   \n"), "a {}\n")

    def test_leading_lines_and_indentation_are_kept(self):
        self.assertEqual(normalize_css("\n  a {}"), "\n  a {}\n")

    def test_empty_values(self):
        self.assertEqual(normalize_css(""), "")
        self.assertEqual(normalize_css(None), "")
        self.assertEqual(normalize_css("\r\n  \n"), "")

    def test_checksum_ignores_line_endings_but_not_content(self):
        self.assertEqual(css_checksum("a {}\r\nb {}"), css_checksum("a {}\nb {}\n"))
        self.assertNotEqual(css_checksum("a {}"), css_checksum("a { }"))
        self.assertEqual(len(css_checksum("")), 64)


class LoadSeedSheetsTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(load_seed_sheets(missing_seed_path(self)), {})

    def test_reads_sheets_by_name(self):
        path = write_seed(self, [seed_record(1, "alpha", "a {}"), seed_record(2, "beta", "b {}", is_active=False)])

        seeds = load_seed_sheets(path)

        self.assertEqual(list(seeds), ["alpha", "beta"])
        self.assertEqual(seeds["alpha"]["css"], "a {}")
        self.assertFalse(seeds["beta"]["is_active"])

    def test_accepts_string_paths(self):
        path = write_seed(self, [seed_record(1, "alpha", "a {}")])
        self.assertEqual(list(load_seed_sheets(str(path))), ["alpha"])

    def test_returns_fresh_dicts_safe_to_mutate(self):
        path = write_seed(self, [seed_record(1, "alpha", "a {}")])

        first = load_seed_sheets(path)
        first["alpha"]["css"] = "mutated"
        first.pop("alpha")

        self.assertEqual(load_seed_sheets(path)["alpha"]["css"], "a {}")

    def test_rereads_the_file_when_its_mtime_changes(self):
        path = write_seed(self, [seed_record(1, "alpha", "a {}")])
        self.assertEqual(load_seed_sheets(path)["alpha"]["css"], "a {}")
        old_mtime = path.stat().st_mtime_ns

        path.write_text(json.dumps([seed_record(1, "alpha", "a { color: red; }")]), encoding="utf-8")
        os.utime(path, ns=(old_mtime + 1_000_000_000, old_mtime + 1_000_000_000))

        self.assertEqual(load_seed_sheets(path)["alpha"]["css"], "a { color: red; }")

    def test_default_path_is_the_repo_seed(self):
        with open(SEED_PATH, encoding="utf-8") as handle:
            names = [record["fields"]["name"] for record in json.load(handle)]

        self.assertEqual(list(load_seed_sheets()), names)


class ChangedSettingsTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.seed = {"css": "a {}", "is_active": True, "sort_order": 10}

    def test_the_seed_managed_fields(self):
        self.assertEqual(SEED_SETTINGS_FIELDS, ("is_active", "sort_order"))

    def test_nothing_changed(self):
        self.assertEqual(changed_settings(StyleSheet(name="a", is_active=True, sort_order=10), self.seed), [])

    def test_each_changed_field_is_listed_in_field_order(self):
        cases = [
            (StyleSheet(name="a", is_active=False, sort_order=10), ["is_active"]),
            (StyleSheet(name="a", is_active=True, sort_order=11), ["sort_order"]),
            (StyleSheet(name="a", is_active=False, sort_order=0), ["is_active", "sort_order"]),
        ]
        for sheet, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(changed_settings(sheet, self.seed), expected)

    def test_css_is_not_a_setting(self):
        sheet = StyleSheet(name="a", css="changed {}", is_active=True, sort_order=10)
        self.assertEqual(changed_settings(sheet, self.seed), [])

    def test_fields_missing_from_the_seed_are_not_compared(self):
        sheet = StyleSheet(name="a", is_active=False, sort_order=99)
        self.assertEqual(changed_settings(sheet, {"css": "a {}"}), [])
        self.assertEqual(changed_settings(sheet, {"css": "a {}", "sort_order": 10}), ["sort_order"])

    def test_no_seed_means_no_changed_settings(self):
        self.assertEqual(changed_settings(StyleSheet(name="a", is_active=False), None), [])


class SheetStatusTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.seeds = {"site": {"name": "site", "css": "body {\n  color: red;\n}\n"}, "empty": {"name": "empty"}}

    def test_in_sync(self):
        self.assertEqual(
            sheet_status(StyleSheet(name="site", css="body {\n  color: red;\n}\n"), self.seeds), STATUS_IN_SYNC
        )

    def test_crlf_and_trailing_whitespace_only_difference_is_in_sync(self):
        sheet = StyleSheet(name="site", css="body {  \r\n  color: red;\r\n}\r\n\r\n")
        self.assertEqual(sheet_status(sheet, self.seeds), STATUS_IN_SYNC)

    def test_edited(self):
        sheet = StyleSheet(name="site", css="body {\n  color: blue;\n}\n")
        self.assertEqual(sheet_status(sheet, self.seeds), STATUS_EDITED)

    def test_seed_without_css_compares_against_empty(self):
        self.assertEqual(sheet_status(StyleSheet(name="empty", css=""), self.seeds), STATUS_IN_SYNC)
        self.assertEqual(sheet_status(StyleSheet(name="empty", css="a {}"), self.seeds), STATUS_EDITED)

    def test_seed_without_settings_ignores_is_active_and_sort_order(self):
        sheet = StyleSheet(name="site", css="body {\n  color: red;\n}\n", is_active=False, sort_order=999)
        self.assertEqual(sheet_status(sheet, self.seeds), STATUS_IN_SYNC)

    def test_unmanaged(self):
        self.assertEqual(sheet_status(StyleSheet(name="custom", css="a {}"), self.seeds), STATUS_UNMANAGED)
        inactive = StyleSheet(name="custom", css="a {}", is_active=False)
        self.assertEqual(sheet_status(inactive, self.seeds), STATUS_UNMANAGED)

    def test_inactive_backup_copies_for_both_suffixes(self):
        for name in ("global-pre-redesign", "global-pre-audit-fixes", "page-news-pre-redesign"):
            with self.subTest(name=name):
                self.assertTrue(is_backup_copy(name))
                sheet = StyleSheet(name=name, css="x {}", is_active=False)
                self.assertEqual(sheet_status(sheet, self.seeds), STATUS_BACKUP_COPY)

    def test_active_backup_copy_is_unmanaged(self):
        # Switching a backup copy back on serves CSS the seed does not hold.
        for name in ("global-pre-redesign", "global-pre-audit-fixes"):
            with self.subTest(name=name):
                sheet = StyleSheet(name=name, css="x {}", is_active=True)
                self.assertEqual(sheet_status(sheet, self.seeds), STATUS_UNMANAGED)

    def test_backup_suffix_in_the_seed_is_compared_like_any_seed_sheet(self):
        seeds = {"global-pre-redesign": {"css": "x {}", "is_active": False, "sort_order": 10}}
        sheet = StyleSheet(name="global-pre-redesign", css="x {}", is_active=False, sort_order=10)
        self.assertEqual(sheet_status(sheet, seeds), STATUS_IN_SYNC)

    def test_suffix_must_be_at_the_end(self):
        self.assertFalse(is_backup_copy("pre-redesign-global"))
        sheet = StyleSheet(name="pre-redesign-global", is_active=False)
        self.assertEqual(sheet_status(sheet, self.seeds), STATUS_UNMANAGED)

    def test_every_status_has_a_label(self):
        self.assertEqual(
            set(STATUS_LABELS),
            {
                STATUS_IN_SYNC,
                STATUS_EDITED,
                STATUS_SETTINGS_CHANGED,
                STATUS_UNMANAGED,
                STATUS_BACKUP_COPY,
                STATUS_RETIRED,
                STATUS_UNKNOWN,
            },
        )


class SettingsChangedStatusTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.seeds = {"site": {"css": "a {}\n", "is_active": True, "sort_order": 10}}

    def test_is_active_differs(self):
        sheet = StyleSheet(name="site", css="a {}\r\n", is_active=False, sort_order=10)
        self.assertEqual(sheet_status(sheet, self.seeds), STATUS_SETTINGS_CHANGED)

    def test_sort_order_differs(self):
        sheet = StyleSheet(name="site", css="a {}", is_active=True, sort_order=15)
        self.assertEqual(sheet_status(sheet, self.seeds), STATUS_SETTINGS_CHANGED)

    def test_matching_settings_are_in_sync(self):
        sheet = StyleSheet(name="site", css="a {}", is_active=True, sort_order=10)
        self.assertEqual(sheet_status(sheet, self.seeds), STATUS_IN_SYNC)

    def test_edited_css_wins_over_changed_settings(self):
        sheet = StyleSheet(name="site", css="b {}", is_active=False, sort_order=15)
        self.assertEqual(sheet_status(sheet, self.seeds), STATUS_EDITED)

    def test_inactive_seed_sheet_left_inactive_is_in_sync(self):
        seeds = {"site": {"css": "a {}", "is_active": False, "sort_order": 10}}
        sheet = StyleSheet(name="site", css="a {}", is_active=False, sort_order=10)
        self.assertEqual(sheet_status(sheet, seeds), STATUS_IN_SYNC)


class SeedStatusLabelTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.seed_path = write_seed(self, [seed_record(1, "alpha", "a {}\n", sort_order=10)])

    def test_label_for_each_status(self):
        cases = [
            (StyleSheet(name="alpha", css="a {}", sort_order=10), STATUS_IN_SYNC),
            (StyleSheet(name="alpha", css="b {}", sort_order=10), STATUS_EDITED),
            (StyleSheet(name="alpha", css="a {}", sort_order=20), STATUS_SETTINGS_CHANGED),
            (StyleSheet(name="alpha", css="a {}", sort_order=10, is_active=False), STATUS_SETTINGS_CHANGED),
            (StyleSheet(name="custom", css="c {}"), STATUS_UNMANAGED),
            (StyleSheet(name="alpha-pre-redesign", css="old {}", is_active=True), STATUS_UNMANAGED),
            (StyleSheet(name="alpha-pre-redesign", css="old {}", is_active=False), STATUS_BACKUP_COPY),
        ]
        for sheet, status in cases:
            with self.subTest(name=sheet.name, status=status):
                self.assertEqual(seed_status_label(sheet, seed_path=self.seed_path), STATUS_LABELS[status])

    def test_unknown_when_the_seed_file_is_missing(self):
        missing = missing_seed_path(self)

        for sheet in (StyleSheet(name="alpha", css="a {}"), StyleSheet(name="custom", css="c {}")):
            with self.subTest(name=sheet.name):
                self.assertEqual(seed_status_label(sheet, seed_path=missing), STATUS_LABELS[STATUS_UNKNOWN])
        self.assertEqual(STATUS_LABELS[STATUS_UNKNOWN], "Unknown (repo seed file not found)")

    def test_default_path_is_the_repo_seed(self):
        seed = load_seed_sheets()["global"]
        sheet = StyleSheet(name="global", css=seed["css"], is_active=False, sort_order=seed["sort_order"])

        self.assertEqual(seed_status_label(sheet), STATUS_LABELS[STATUS_RETIRED])


class DescribeSheetTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.seeds = {"site": {"css": "a {}\nb {}\nc {}\n"}}

    def test_in_sync_sheet_has_no_diff(self):
        sheet = StyleSheet(name="site", display_name="Global", css="a {}\r\nb {}\r\nc {}", sort_order=10)

        self.assertEqual(
            describe_sheet(sheet, self.seeds),
            {
                "name": "site",
                "display_name": "Global",
                "is_active": True,
                "sort_order": 10,
                "status": STATUS_IN_SYNC,
                "changed_settings": [],
                "added_lines": 0,
                "removed_lines": 0,
                "diff": "",
            },
        )

    def test_edited_sheet_counts_lines_and_carries_a_unified_diff(self):
        sheet = StyleSheet(name="site", display_name="Global", css="a {}\nB {}\nc {}\nd {}\n", is_active=False)

        entry = describe_sheet(sheet, self.seeds)

        self.assertEqual(entry["status"], STATUS_EDITED)
        self.assertFalse(entry["is_active"])
        self.assertEqual(entry["added_lines"], 2)
        self.assertEqual(entry["removed_lines"], 1)
        self.assertTrue(entry["diff"].startswith("--- seed/site.css\n+++ database/site.css\n"))
        self.assertIn("\n-b {}\n", entry["diff"])
        self.assertIn("\n+B {}\n", entry["diff"])
        self.assertIn("\n+d {}\n", entry["diff"])

    def test_settings_changed_sheet_lists_the_fields_and_has_no_diff(self):
        seeds = {"site": {"css": "a {}\n", "is_active": True, "sort_order": 10}}
        sheet = StyleSheet(name="site", display_name="Global", css="a {}", is_active=False, sort_order=12)

        entry = describe_sheet(sheet, seeds)

        self.assertEqual(entry["status"], STATUS_SETTINGS_CHANGED)
        self.assertEqual(entry["changed_settings"], ["is_active", "sort_order"])
        self.assertEqual((entry["diff"], entry["added_lines"], entry["removed_lines"]), ("", 0, 0))

    def test_edited_sheet_also_lists_changed_settings(self):
        seeds = {"site": {"css": "a {}\n", "is_active": True, "sort_order": 10}}
        sheet = StyleSheet(name="site", css="b {}\n", is_active=True, sort_order=12)

        entry = describe_sheet(sheet, seeds)

        self.assertEqual((entry["status"], entry["changed_settings"]), (STATUS_EDITED, ["sort_order"]))
        self.assertEqual((entry["added_lines"], entry["removed_lines"]), (1, 1))

    def test_unmanaged_and_backup_sheets_have_no_diff_or_changed_settings(self):
        for name, active in (("custom", True), ("global-pre-redesign", False), ("global-pre-redesign", True)):
            with self.subTest(name=name, active=active):
                entry = describe_sheet(StyleSheet(name=name, css="z {}", is_active=active), self.seeds)
                self.assertEqual((entry["diff"], entry["added_lines"], entry["removed_lines"]), ("", 0, 0))
                self.assertEqual(entry["changed_settings"], [])

    def test_sheet_diff_ignores_line_ending_noise(self):
        self.assertEqual(sheet_diff(StyleSheet(name="site", css="a {}\r\n"), "a {}\n"), "")

    def test_removed_custom_property_line_is_counted(self):
        # The diff line of a removed "--x: 1;" starts with "---", like the file header.
        sheet = StyleSheet(name="site", css=":root {\n--x: 2;\n}\n")
        entry = describe_sheet(sheet, {"site": {"css": ":root {\n--x: 1;\n}\n"}})
        self.assertIn("\n---x: 1;\n", entry["diff"])
        self.assertEqual((entry["added_lines"], entry["removed_lines"]), (1, 1))

    def test_only_removed_custom_properties(self):
        sheet = StyleSheet(name="site", css=":root {\n}\n")
        entry = describe_sheet(sheet, {"site": {"css": ":root {\n--x: 1;\n--y: 2;\n}\n"}})
        self.assertEqual((entry["added_lines"], entry["removed_lines"]), (0, 2))

    def test_changes_in_several_hunks_are_summed(self):
        seed_css = "".join(f"r{index} {{}}\n" for index in range(20))
        db_css = seed_css.replace("r1 {}", "R1 {}").replace("r18 {}\n", "")
        entry = describe_sheet(StyleSheet(name="site", css=db_css), {"site": {"css": seed_css}})

        self.assertEqual(entry["diff"].count("\n@@ "), 2)
        self.assertEqual((entry["added_lines"], entry["removed_lines"]), (1, 2))


class PagesWithCssTests(TestCase):
    def setUp(self):
        cache.clear()
        # Migration cms.0023 seeds the /acknowledgement page; start from no pages.
        CMSPage.objects.all().delete()

    def test_lists_only_pages_with_css_ordered_by_route(self):
        CMSPage.objects.create(slug="zeta", route="/zeta", title="Zeta", page_css=".z { color: red; }")
        CMSPage.objects.create(slug="plain", route="/plain", title="Plain")
        CMSPage.objects.create(slug="about", route="/about", title="About", page_css=".a {}", status="published")

        self.assertEqual(
            pages_with_css(),
            [
                {"slug": "about", "route": "/about", "status": "published", "page_css_length": 5},
                {"slug": "zeta", "route": "/zeta", "status": "draft", "page_css_length": 18},
            ],
        )

    def test_no_pages_with_css(self):
        CMSPage.objects.create(slug="plain", route="/plain", title="Plain")
        self.assertEqual(pages_with_css(), [])


class DriftReportTests(TestCase):
    def setUp(self):
        cache.clear()
        StyleSheet.objects.all().delete()
        CMSPage.objects.all().delete()
        self.seed_path = write_seed(
            self,
            [
                seed_record(1, "alpha", "a {}\n", sort_order=10),
                seed_record(2, "beta", "b {}\n", sort_order=20),
                seed_record(3, "gamma", "g {}\n", sort_order=30),
                seed_record(4, "delta", "d {}\n", sort_order=40),
            ],
        )

    def test_report_with_every_status(self):
        StyleSheet.objects.create(name="alpha", display_name="Alpha", css="a {}\r\n", sort_order=10)
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b { color: red; }\n", sort_order=20)
        StyleSheet.objects.create(name="delta", display_name="Delta", css="d {}\n", sort_order=45)
        StyleSheet.objects.create(name="custom", display_name="Custom", css="c {}", sort_order=25)
        StyleSheet.objects.create(
            name="alpha-pre-redesign", display_name="Alpha (old)", css="old {}", sort_order=10, is_active=False
        )
        CMSPage.objects.create(slug="styled", route="/styled", title="Styled", page_css=".s {}")

        report = drift_report(seed_path=self.seed_path)

        self.assertEqual(report["seed_path"], str(self.seed_path))
        self.assertTrue(report["seed_found"])
        self.assertEqual(
            [(entry["name"], entry["status"], entry["changed_settings"]) for entry in report["sheets"]],
            [
                ("alpha", STATUS_IN_SYNC, []),
                ("alpha-pre-redesign", STATUS_BACKUP_COPY, []),
                ("beta", STATUS_EDITED, []),
                ("custom", STATUS_UNMANAGED, []),
                ("delta", STATUS_SETTINGS_CHANGED, ["sort_order"]),
            ],
        )
        beta = report["sheets"][2]
        self.assertEqual((beta["added_lines"], beta["removed_lines"]), (1, 1))
        self.assertIn("+b { color: red; }", beta["diff"])
        self.assertEqual(report["missing_from_database"], ["gamma"])
        # gamma is active in the seed, so a re-sync migration would recreate and serve it again.
        self.assertEqual(report["deleted_active_seed_sheets"], ["gamma"])
        self.assertEqual(
            report["counts"],
            {
                STATUS_IN_SYNC: 1,
                STATUS_BACKUP_COPY: 1,
                STATUS_EDITED: 1,
                STATUS_UNMANAGED: 1,
                STATUS_SETTINGS_CHANGED: 1,
            },
        )
        self.assertEqual(
            report["pages_with_css"],
            [{"slug": "styled", "route": "/styled", "status": "draft", "page_css_length": 5}],
        )
        self.assertEqual(drifted_sheets(report), ["beta", "custom", "delta", "gamma (deleted)"])
        self.assertTrue(has_drift(report))
        json.dumps(report)  # The command prints the report as JSON.

    def test_empty_database_reports_every_seed_sheet_missing(self):
        report = drift_report(seed_path=self.seed_path)

        self.assertEqual(report["sheets"], [])
        self.assertEqual(report["missing_from_database"], ["alpha", "beta", "gamma", "delta"])
        self.assertEqual(report["deleted_active_seed_sheets"], ["alpha", "beta", "gamma", "delta"])
        self.assertEqual(report["counts"], {})
        self.assertTrue(report["seed_found"])
        self.assertEqual(
            drifted_sheets(report), ["alpha (deleted)", "beta (deleted)", "gamma (deleted)", "delta (deleted)"]
        )
        self.assertTrue(has_drift(report))

    def test_deleted_seed_sheet_that_is_inactive_in_the_seed_is_not_drift(self):
        seed_path = write_seed(
            self,
            [
                seed_record(1, "alpha", "a {}\n", sort_order=10),
                seed_record(2, "omega", "o {}\n", sort_order=20, is_active=False),
            ],
        )
        StyleSheet.objects.create(name="alpha", display_name="Alpha", css="a {}\n", sort_order=10)

        report = drift_report(seed_path=seed_path)

        self.assertEqual(report["missing_from_database"], ["omega"])
        self.assertEqual(report["deleted_active_seed_sheets"], [])
        self.assertEqual(drifted_sheets(report), [])
        self.assertFalse(has_drift(report))

    def test_seed_record_without_is_active_counts_as_active_when_deleted(self):
        record = seed_record(1, "alpha", "a {}\n")
        del record["fields"]["is_active"]
        seed_path = write_seed(self, [record])

        report = drift_report(seed_path=seed_path)

        self.assertEqual(report["deleted_active_seed_sheets"], ["alpha"])
        self.assertEqual(drifted_sheets(report), ["alpha (deleted)"])

    def test_missing_seed_file_is_flagged_and_every_sheet_is_unmanaged(self):
        StyleSheet.objects.create(name="alpha", display_name="Alpha", css="a {}")
        missing = self.seed_path.parent / "missing.json"

        report = drift_report(seed_path=missing)

        self.assertEqual(report["seed_path"], str(missing))
        self.assertFalse(report["seed_found"])
        self.assertEqual(report["sheets"][0]["status"], STATUS_UNMANAGED)
        self.assertEqual(report["missing_from_database"], [])
        self.assertEqual(report["deleted_active_seed_sheets"], [])

    def test_default_seed_path(self):
        report = drift_report()

        self.assertEqual(report["seed_path"], str(SEED_PATH))
        self.assertTrue(report["seed_found"])


def report_entry(name, active, status, settings=()):
    return {"name": name, "is_active": active, "status": status, "changed_settings": list(settings)}


class IsDriftedTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_which_entries_drifted(self):
        cases = [
            (report_entry("a", True, STATUS_EDITED), True),
            (report_entry("a", True, STATUS_UNMANAGED), True),
            (report_entry("a", True, STATUS_SETTINGS_CHANGED, ["sort_order"]), True),
            (report_entry("a", False, STATUS_SETTINGS_CHANGED, ["is_active"]), True),
            (report_entry("a", False, STATUS_EDITED, ["is_active"]), True),
            (report_entry("a", False, STATUS_EDITED), False),
            (report_entry("a", False, STATUS_UNMANAGED), False),
            (report_entry("a", False, STATUS_BACKUP_COPY), False),
            (report_entry("a", True, STATUS_IN_SYNC), False),
            (report_entry("a", False, STATUS_IN_SYNC), False),
        ]
        for entry, expected in cases:
            with self.subTest(entry=entry):
                self.assertIs(is_drifted(entry), expected)

    def test_drifted_sheets_keeps_report_order(self):
        report = {
            "sheets": [
                report_entry("z", True, STATUS_EDITED),
                report_entry("in-sync", True, STATUS_IN_SYNC),
                report_entry("a", True, STATUS_UNMANAGED),
                report_entry("m", True, STATUS_SETTINGS_CHANGED, ["is_active"]),
                report_entry("old", False, STATUS_EDITED),
            ]
        }

        self.assertEqual(drifted_sheets(report), ["z", "a", "m"])
        self.assertTrue(has_drift(report))

    def test_deleted_active_seed_sheets_are_appended_with_a_marker(self):
        report = {
            "sheets": [report_entry("in-sync", True, STATUS_IN_SYNC), report_entry("z", True, STATUS_EDITED)],
            "deleted_active_seed_sheets": ["alpha", "beta"],
        }

        self.assertEqual(drifted_sheets(report), ["z", "alpha (deleted)", "beta (deleted)"])
        self.assertTrue(has_drift(report))

    def test_hand_built_report_without_the_deleted_key_still_works(self):
        # Reports built by hand (as in the other tests here) have no "deleted_active_seed_sheets" key.
        report = {"sheets": [report_entry("z", True, STATUS_EDITED), report_entry("a", True, STATUS_IN_SYNC)]}

        self.assertEqual(drifted_sheets(report), ["z"])
        self.assertTrue(has_drift(report))

    def test_has_drift_matches_drifted_sheets(self):
        cases = [
            ((report_entry("a", True, STATUS_IN_SYNC),), False),
            ((report_entry("a", False, STATUS_UNMANAGED), report_entry("b", False, STATUS_BACKUP_COPY)), False),
            ((report_entry("a", True, STATUS_IN_SYNC), report_entry("b", True, STATUS_EDITED)), True),
            ((), False),
        ]
        for entries, expected in cases:
            with self.subTest(entries=entries):
                report = {"sheets": list(entries)}
                self.assertIs(has_drift(report), expected)
                self.assertEqual(bool(drifted_sheets(report)), expected)


class HasDriftDatabaseTests(TestCase):
    def setUp(self):
        cache.clear()
        StyleSheet.objects.all().delete()
        self.seed_path = write_seed(
            self,
            [
                seed_record(1, "alpha", "a {}", sort_order=10, is_active=False),
                seed_record(2, "beta", "b {}", sort_order=20),
            ],
        )

    def _report(self):
        return drift_report(seed_path=self.seed_path)

    def test_inactive_rows_nobody_serves_are_not_drift(self):
        # alpha is inactive in the seed too, so its edit is not served and not re-activated by a re-sync.
        StyleSheet.objects.create(
            name="alpha", display_name="Alpha", css="a { color: red; }", sort_order=10, is_active=False
        )
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}", sort_order=20)
        StyleSheet.objects.create(name="old", display_name="Old", css="o {}", is_active=False)
        StyleSheet.objects.create(name="beta-pre-redesign", display_name="Beta (old)", css="o {}", is_active=False)

        report = self._report()

        self.assertEqual(
            report["counts"], {STATUS_EDITED: 1, STATUS_IN_SYNC: 1, STATUS_UNMANAGED: 1, STATUS_BACKUP_COPY: 1}
        )
        self.assertEqual(drifted_sheets(report), [])
        self.assertFalse(has_drift(report))

        StyleSheet.objects.filter(name="alpha").update(is_active=True)
        report = self._report()
        self.assertEqual(drifted_sheets(report), ["alpha"])
        alpha = next(entry for entry in report["sheets"] if entry["name"] == "alpha")
        self.assertEqual((alpha["status"], alpha["changed_settings"]), (STATUS_EDITED, ["is_active"]))

    def test_deactivated_seed_sheet_is_drift(self):
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}", sort_order=20, is_active=False)

        report = self._report()

        self.assertEqual(report["sheets"][0]["status"], STATUS_SETTINGS_CHANGED)
        self.assertEqual(report["sheets"][0]["changed_settings"], ["is_active"])
        self.assertEqual(drifted_sheets(report), ["beta"])

    def test_reordered_seed_sheet_is_drift(self):
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}", sort_order=5)

        report = self._report()

        self.assertEqual(report["sheets"][0]["status"], STATUS_SETTINGS_CHANGED)
        self.assertEqual(report["sheets"][0]["changed_settings"], ["sort_order"])
        self.assertTrue(has_drift(report))

    def test_deleted_active_seed_sheet_is_drift(self):
        # alpha is inactive in the seed, so deleting it changes nothing a re-sync would serve.
        report = self._report()

        self.assertEqual(report["missing_from_database"], ["alpha", "beta"])
        self.assertEqual(report["deleted_active_seed_sheets"], ["beta"])
        self.assertEqual(drifted_sheets(report), ["beta (deleted)"])

        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}", sort_order=20)
        report = self._report()
        self.assertEqual((report["missing_from_database"], report["deleted_active_seed_sheets"]), (["alpha"], []))
        self.assertFalse(has_drift(report))

    def test_active_backup_copy_is_unmanaged_drift(self):
        StyleSheet.objects.create(name="beta", display_name="Beta", css="b {}", sort_order=20)
        StyleSheet.objects.create(name="beta-pre-audit-fixes", display_name="Beta (old)", css="o {}", sort_order=21)

        report = self._report()

        statuses = {entry["name"]: entry["status"] for entry in report["sheets"]}
        self.assertEqual(statuses, {"beta": STATUS_IN_SYNC, "beta-pre-audit-fixes": STATUS_UNMANAGED})
        self.assertEqual(drifted_sheets(report), ["beta-pre-audit-fixes"])


class ExportRowsTests(TestCase):
    def setUp(self):
        cache.clear()
        StyleSheet.objects.all().delete()
        CMSPage.objects.all().delete()

    def test_export_shape(self):
        StyleSheet.objects.create(name="z", display_name="Z", css="z {}", sort_order=20)
        StyleSheet.objects.create(
            name="a", display_name="A", description="First", css="a {}", sort_order=10, is_active=False
        )
        CMSPage.objects.create(slug="styled", route="/styled", title="Styled", page_css=".s {}")
        CMSPage.objects.create(slug="plain", route="/plain", title="Plain")

        bundle = export_rows()

        self.assertEqual(set(bundle), {"version", "exported_at", "stylesheets", "pages_with_css"})
        self.assertEqual(bundle["version"], 1)
        self.assertIsInstance(datetime.fromisoformat(bundle["exported_at"]), datetime)
        self.assertEqual(
            bundle["stylesheets"],
            [
                {
                    "name": "a",
                    "display_name": "A",
                    "description": "First",
                    "css": "a {}",
                    "is_active": False,
                    "sort_order": 10,
                },
                {
                    "name": "z",
                    "display_name": "Z",
                    "description": "",
                    "css": "z {}",
                    "is_active": True,
                    "sort_order": 20,
                },
            ],
        )
        self.assertEqual(bundle["pages_with_css"], [{"slug": "styled", "route": "/styled", "page_css": ".s {}"}])
        json.dumps(bundle)

    def test_empty_database(self):
        bundle = export_rows()
        self.assertEqual((bundle["stylesheets"], bundle["pages_with_css"]), ([], []))
