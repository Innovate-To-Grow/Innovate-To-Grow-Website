from django.db.models import NOT_PROVIDED

from apps.cli_admin.services.schema import field_schema_verbose
from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff


class SchemaVerboseEndpointTests(CliApiTestCase):
    """The schema endpoint enriches each field dict without changing the
    top-level ``{model, primary_key, readable_fields, writable_fields}`` shape."""

    def setUp(self):
        super().setUp()
        self.staff = make_staff(email="schema@example.com")
        _, self.raw = issue_token(self.staff)

    def _schema(self, app_label, model_name):
        response = self.client.get(f"/admin-api/models/{app_label}/{model_name}/schema/", **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        return response.data

    @staticmethod
    def _by_name(fields):
        return {field["name"]: field for field in fields}

    def test_top_level_shape_unchanged(self):
        data = self._schema("projects", "semester")
        self.assertEqual(set(data), {"model", "primary_key", "readable_fields", "writable_fields"})
        self.assertEqual(data["model"], "projects.Semester")
        self.assertEqual(data["primary_key"], "id")

    def test_choices_field_is_structured(self):
        # Semester.season is an IntegerChoices field; choices become [{value, label}].
        data = self._schema("projects", "semester")
        season = self._by_name(data["writable_fields"])["season"]
        self.assertEqual(season["choices"], [{"value": 1, "label": "Spring"}, {"value": 2, "label": "Fall"}])
        # Base keys from the shared field_schema are preserved alongside the new ones.
        self.assertEqual(season["type"], "PositiveSmallIntegerField")
        self.assertTrue(season["required"])
        self.assertEqual(season["verbose_name"], "season")
        self.assertFalse(season["blank"])
        self.assertFalse(season["null"])

    def test_concrete_default_is_included(self):
        data = self._schema("projects", "semester")
        writable = self._by_name(data["writable_fields"])
        self.assertEqual(writable["label"]["default"], "")
        self.assertEqual(writable["is_published"]["default"], False)

    def test_default_omitted_when_unset_or_callable(self):
        data = self._schema("projects", "semester")
        # year has no default at all -> the key is absent (NOT_PROVIDED is skipped).
        self.assertNotIn("default", self._by_name(data["writable_fields"])["year"])

    def test_nullable_field_flags(self):
        # Project.track is null=True, blank=True with no default.
        data = self._schema("projects", "project")
        track = self._by_name(data["writable_fields"])["track"]
        self.assertTrue(track["null"])
        self.assertTrue(track["blank"])
        self.assertNotIn("default", track)

    def test_foreign_key_exposes_target(self):
        data = self._schema("projects", "project")
        semester = self._by_name(data["writable_fields"])["semester_id"]
        self.assertEqual(semester["type"], "ForeignKey")
        self.assertEqual(semester["related_model"], "projects.Semester")
        self.assertEqual(semester["related_pk"], "id")

    def test_help_text_included_when_present(self):
        # SiteMaintenanceControl fields carry help_text; non-empty help_text is surfaced.
        data = self._schema("core", "sitemaintenancecontrol")
        is_maintenance = self._by_name(data["writable_fields"])["is_maintenance"]
        self.assertTrue(is_maintenance["help_text"])


class _FakeField:
    """A minimal field stand-in for exercising field_schema_verbose's defensive
    guards that real Django fields never trigger (missing verbose_name; a relation
    with no resolvable target_field)."""

    def __init__(self, **attrs):
        self.name = attrs.pop("name", "fake")
        self.attname = self.name
        self.blank = attrs.pop("blank", False)
        self.null = attrs.pop("null", False)
        self.choices = attrs.pop("choices", None)
        self.default = attrs.pop("default", NOT_PROVIDED)
        self.has_default_value = self.default is not NOT_PROVIDED
        for key, value in attrs.items():
            setattr(self, key, value)

    # field_schema (shared) calls these.
    def has_default(self):
        return self.has_default_value


class FieldSchemaVerboseDefensiveTests(CliApiTestCase):
    def test_missing_verbose_name_is_skipped(self):
        field = _FakeField(name="bare", verbose_name=None)
        schema = field_schema_verbose(field, write=False)
        self.assertNotIn("verbose_name", schema)

    def test_relation_without_target_field_skips_related_pk(self):
        class _Meta:
            label = "fake.Target"

        class _Related:
            _meta = _Meta()

        field = _FakeField(
            name="rel",
            verbose_name="rel",
            is_relation=True,
            related_model=_Related,
            target_field=None,
        )
        schema = field_schema_verbose(field, write=False)
        self.assertEqual(schema["related_model"], "fake.Target")
        self.assertNotIn("related_pk", schema)
