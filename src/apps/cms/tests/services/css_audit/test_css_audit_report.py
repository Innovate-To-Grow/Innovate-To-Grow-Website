"""Tests for ``audit_css_classes`` and ``is_undefined`` in ``apps.cms.services.styles.audit`` (the report rows)."""

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.audit import is_undefined

REPORT_KEYS = {
    "frontend_scanned",
    "frontend_dir",
    "frontend_import_graph",
    "total_classes",
    "undefined_classes",
    "classes",
}
ROW_KEYS = {
    "class_name",
    "usage_count",
    "pages",
    "footers",
    "sources",
    "block_types",
    "frontend_files",
    "route_frontend_files",
    "scoped_in",
    "hook_in",
    "defined",
}


class IsUndefinedTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_undefined_means_no_site_wide_definition_and_no_hook(self):
        self.assertTrue(is_undefined({"defined": False, "hook_in": []}))
        self.assertFalse(is_undefined({"defined": True, "hook_in": []}))
        self.assertFalse(is_undefined({"defined": False, "hook_in": ["styles/events.css"]}))
        self.assertFalse(is_undefined({"defined": True, "hook_in": ["index.css"]}))
