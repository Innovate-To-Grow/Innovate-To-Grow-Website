"""Tests for confirm_on_save_utils helper functions."""

import uuid
from datetime import date, datetime
from unittest.mock import MagicMock

from django.http import QueryDict
from django.test import TestCase
from django.utils import timezone

from core.admin.mixins.confirm_on_save_utils import (
    compute_add_diff,
    compute_change_diff,
    compute_delete_diff,
    deserialize_post_data,
    format_field_value,
    serialize_post_data,
)


class SerializePostDataTest(TestCase):
    def test_roundtrip_simple_data(self):
        qd = QueryDict(mutable=True)
        qd["name"] = "Hello"
        qd["active"] = "on"

        serialized = serialize_post_data(qd)
        restored = deserialize_post_data(serialized)

        self.assertEqual(restored["name"], "Hello")
        self.assertEqual(restored["active"], "on")

    def test_roundtrip_multi_value_keys(self):
        qd = QueryDict(mutable=True)
        qd.setlist("tags", ["python", "django", "admin"])

        serialized = serialize_post_data(qd)
        restored = deserialize_post_data(serialized)

        self.assertEqual(restored.getlist("tags"), ["python", "django", "admin"])

    def test_empty_querydict(self):
        qd = QueryDict(mutable=True)
        serialized = serialize_post_data(qd)
        restored = deserialize_post_data(serialized)

        self.assertEqual(len(restored), 0)


class FormatFieldValueTest(TestCase):
    def test_none_returns_dash(self):
        self.assertEqual(format_field_value(None), "-")

    def test_bool_true(self):
        self.assertEqual(format_field_value(True), "Yes")

    def test_bool_false(self):
        self.assertEqual(format_field_value(False), "No")

    def test_datetime_formatted(self):
        dt = datetime(2025, 6, 15, 10, 30, 0)
        result = format_field_value(dt)
        self.assertIn("2025-06-15", result)
        self.assertIn("10:30:00", result)

    def test_aware_datetime_includes_timezone(self):
        dt = timezone.now()
        result = format_field_value(dt)
        self.assertIn("UTC", result)

    def test_date_formatted(self):
        d = date(2025, 3, 15)
        self.assertEqual(format_field_value(d), "2025-03-15")

    def test_uuid_as_string(self):
        u = uuid.uuid4()
        self.assertEqual(format_field_value(u), str(u))

    def test_model_instance_uses_str(self):
        obj = MagicMock()
        obj.__str__ = MagicMock(return_value="Mock Object Name")
        self.assertEqual(format_field_value(obj), "Mock Object Name")

    def test_list_serialized_as_json(self):
        result = format_field_value([1, 2, 3])
        self.assertEqual(result, "[1, 2, 3]")

    def test_dict_serialized_as_json(self):
        result = format_field_value({"key": "value"})
        self.assertIn('"key"', result)
        self.assertIn('"value"', result)

    def test_long_string_truncated(self):
        long_str = "x" * 300
        result = format_field_value(long_str)
        self.assertEqual(len(result), 203)  # 200 + "..."
        self.assertTrue(result.endswith("..."))

    def test_short_string_not_truncated(self):
        self.assertEqual(format_field_value("short"), "short")

    def test_integer(self):
        self.assertEqual(format_field_value(42), "42")


class ComputeAddDiffTest(TestCase):
    def test_returns_all_fields_with_values(self):
        form = MagicMock()
        form.fields = {"name": MagicMock(label="Name"), "active": MagicMock(label="Active")}
        form.cleaned_data = {"name": "Test", "active": True}

        diff = compute_add_diff(form)

        self.assertEqual(len(diff), 2)
        self.assertEqual(diff[0]["field"], "name")
        self.assertEqual(diff[0]["new_value"], "Test")
        self.assertEqual(diff[1]["field"], "active")
        self.assertEqual(diff[1]["new_value"], "Yes")

    def test_skips_fields_not_in_cleaned_data(self):
        form = MagicMock()
        form.fields = {"name": MagicMock(label="Name"), "hidden": MagicMock(label="Hidden")}
        form.cleaned_data = {"name": "Test"}

        diff = compute_add_diff(form)

        self.assertEqual(len(diff), 1)
        self.assertEqual(diff[0]["field"], "name")

    def test_uses_field_name_when_label_is_none(self):
        form = MagicMock()
        form.fields = {"slug": MagicMock(label=None)}
        form.cleaned_data = {"slug": "my-slug"}

        diff = compute_add_diff(form)

        self.assertEqual(diff[0]["label"], "slug")


class ComputeChangeDiffTest(TestCase):
    def test_returns_changed_fields_only(self):
        from cms.models import CMSEmbedAllowedHost

        obj = CMSEmbedAllowedHost.objects.create(hostname="old.com", is_active=True)

        form = MagicMock()
        form.changed_data = ["hostname"]
        form.fields = {"hostname": MagicMock(label="Hostname")}
        form.cleaned_data = {"hostname": "new.com"}

        diff = compute_change_diff(CMSEmbedAllowedHost, obj.pk, form)

        self.assertEqual(len(diff), 1)
        self.assertEqual(diff[0]["old_value"], "old.com")
        self.assertEqual(diff[0]["new_value"], "new.com")

    def test_empty_changed_data_returns_empty(self):
        from cms.models import CMSEmbedAllowedHost

        form = MagicMock()
        form.changed_data = []

        diff = compute_change_diff(CMSEmbedAllowedHost, "fake-id", form)

        self.assertEqual(diff, [])

    def test_nonexistent_object_returns_empty(self):
        from cms.models import CMSEmbedAllowedHost

        form = MagicMock()
        form.changed_data = ["hostname"]
        form.fields = {"hostname": MagicMock(label="Hostname")}
        form.cleaned_data = {"hostname": "new.com"}

        diff = compute_change_diff(CMSEmbedAllowedHost, uuid.uuid4(), form)

        self.assertEqual(diff, [])


class ComputeDeleteDiffTest(TestCase):
    def test_returns_field_values_for_object(self):
        from cms.models import CMSEmbedAllowedHost

        obj = CMSEmbedAllowedHost.objects.create(hostname="delete-me.com", is_active=True)

        diff = compute_delete_diff(obj)

        field_names = [d["field"] for d in diff]
        self.assertIn("hostname", field_names)
        self.assertIn("is_active", field_names)

        hostname_entry = next(d for d in diff if d["field"] == "hostname")
        self.assertEqual(hostname_entry["value"], "delete-me.com")

    def test_excludes_id_field(self):
        from cms.models import CMSEmbedAllowedHost

        obj = CMSEmbedAllowedHost.objects.create(hostname="no-id.com", is_active=True)

        diff = compute_delete_diff(obj)

        field_names = [d["field"] for d in diff]
        self.assertNotIn("id", field_names)
