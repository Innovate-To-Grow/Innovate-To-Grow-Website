"""Core-owned tests for the promoted shared safe-ORM layer (the model-access
denylist, write validation, serialization, snapshot, and cascade primitives)."""

import uuid

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, tag

from apps.cms.models import CMSAsset, CMSBlock
from apps.core.services.db_tools.safe_orm import (
    ActionRequestError,
    assign_model_fields,
    coerce_field_value,
    field_output_name,
    field_schema,
    is_field_denied,
    is_model_denied,
    resolve_model,
    safe_model_fields,
    validate_query_key,
    validate_selected_fields,
    validate_write_payload,
)
from apps.mail.models import LoginLinkToken
from apps.projects.models import Project, Semester

Member = get_user_model()


@tag("safe_orm")
class SafetyTests(TestCase):
    def safe_names(self):
        return {field_output_name(f) for f in safe_model_fields(Semester, write=False)}

    def test_resolve_model_ok(self):
        self.assertIs(resolve_model("projects", "semester", write=True), Semester)

    def test_resolve_model_unknown_raises(self):
        with self.assertRaises(ActionRequestError):
            resolve_model("projects", "doesnotexist", write=False)

    def test_resolve_model_denied_read(self):
        with self.assertRaises(ActionRequestError):
            resolve_model("admin", "logentry", write=False)

    def test_resolve_model_denied_write(self):
        with self.assertRaises(ActionRequestError):
            resolve_model("admin", "logentry", write=True)

    def test_is_model_denied_variants(self):
        self.assertTrue(is_model_denied(LogEntry, write=False))  # denied app
        self.assertTrue(is_model_denied(Group, write=False))  # denied label
        self.assertTrue(is_model_denied(LoginLinkToken, write=False))  # denied name part "token"
        self.assertFalse(is_model_denied(Semester, write=False))

    def test_safe_model_fields_excludes_filefield(self):
        names = {field_output_name(f) for f in safe_model_fields(CMSAsset, write=False)}
        self.assertNotIn("file", names)

    def test_is_field_denied_branches(self):
        self.assertTrue(is_field_denied(Member._meta.get_field("is_staff"), write=True))  # denied name
        self.assertTrue(is_field_denied(Member._meta.get_field("password"), write=True))  # sensitive regex
        self.assertTrue(is_field_denied(Semester._meta.get_field("id"), write=True))  # pk on write
        self.assertTrue(is_field_denied(Semester._meta.get_field("updated_at"), write=True))  # auto_now
        self.assertFalse(is_field_denied(Semester._meta.get_field("year"), write=True))

    def test_is_field_denied_auto_now_guard_is_independent_of_editable(self):
        # Defense-in-depth: the auto_now guard rejects an auto-timestamp field on
        # write even if it were (artificially) editable, independent of the
        # earlier non-editable guard.
        from django.db import models

        field = models.DateTimeField(auto_now=True)
        field.set_attributes_from_name("touched")
        field.editable = True
        self.assertTrue(is_field_denied(field, write=True))

    def test_field_output_name(self):
        self.assertEqual(field_output_name(Project._meta.get_field("semester")), "semester_id")
        self.assertEqual(field_output_name(Semester._meta.get_field("year")), "year")

    def test_field_schema_includes_choices(self):
        schema = field_schema(Semester._meta.get_field("season"))
        self.assertEqual(schema["name"], "season")
        self.assertTrue(schema["choices"])

    def test_validate_selected_fields(self):
        with self.assertRaises(ActionRequestError):
            validate_selected_fields("year", self.safe_names())
        with self.assertRaises(ActionRequestError):
            validate_selected_fields(["bogus"], self.safe_names())
        self.assertEqual(validate_selected_fields(["year"], self.safe_names()), ["year"])

    def test_validate_query_key(self):
        names = self.safe_names()
        with self.assertRaises(ActionRequestError):
            validate_query_key(5, names)
        with self.assertRaises(ActionRequestError):
            validate_query_key("bogus", names)
        with self.assertRaises(ActionRequestError):
            validate_query_key("year__boguslookup", names)
        validate_query_key("year", names)
        validate_query_key("year__gte", names)
        validate_query_key("-year", names)

    def test_validate_write_payload(self):
        with self.assertRaises(ActionRequestError):
            validate_write_payload(Semester, {"id": "x"})
        self.assertEqual(validate_write_payload(Semester, {"year": 2030}), {"year": 2030})

    def test_assign_model_fields(self):
        obj = Semester()
        assign_model_fields(obj, {"year": 2030, "season": 1})
        self.assertEqual(obj.year, 2030)

    def test_coerce_field_value_branches(self):
        year = Semester._meta.get_field("year")
        self.assertIsNone(coerce_field_value(year, None))
        self.assertEqual(coerce_field_value(CMSBlock._meta.get_field("data"), {"a": 1}), {"a": 1})
        pk = uuid.uuid4()
        self.assertEqual(coerce_field_value(Project._meta.get_field("semester"), str(pk)), pk)
        self.assertEqual(coerce_field_value(year, "2030"), 2030)
