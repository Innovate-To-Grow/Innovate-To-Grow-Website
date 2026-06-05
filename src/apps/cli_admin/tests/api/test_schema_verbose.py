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


class _ExplodingLabel:
    """A choice label whose ``str()`` raises. The shared ``field_schema`` only
    reads ``choice[0]`` (the value), so it stays happy; ``_flatten_choices`` calls
    ``str(label)`` outside its inner guard, so it raises and exercises
    ``field_schema_verbose``'s outer defensive ``except``."""

    def __str__(self):
        raise RuntimeError("label str() exploded")


class FieldSchemaVerboseDefensiveTests(CliApiTestCase):
    def test_missing_verbose_name_is_skipped(self):
        field = _FakeField(name="bare", verbose_name=None)
        schema = field_schema_verbose(field)
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
        schema = field_schema_verbose(field)
        self.assertEqual(schema["related_model"], "fake.Target")
        self.assertNotIn("related_pk", schema)

    def test_flat_choices_become_structured(self):
        field = _FakeField(name="flat", verbose_name="flat", choices=[("a", "A"), ("b", "B")])
        schema = field_schema_verbose(field)
        self.assertEqual(schema["choices"], [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}])

    def test_grouped_optgroup_choices_are_flattened(self):
        # Django 5.2 normalizes optgroup choices to [("Group", [(v, l), ...])]; the
        # inner pairs must be expanded, not stringified into the label.
        field = _FakeField(
            name="grouped",
            verbose_name="grouped",
            choices=[("Group A", [("a", "A"), ("b", "B")]), ("Group B", [("c", "C")])],
        )
        schema = field_schema_verbose(field)
        self.assertEqual(
            schema["choices"],
            [
                {"value": "a", "label": "A"},
                {"value": "b", "label": "B"},
                {"value": "c", "label": "C"},
            ],
        )

    def test_mixed_flat_and_grouped_choices(self):
        field = _FakeField(
            name="mixed",
            verbose_name="mixed",
            choices=[("x", "X"), ("Group", [("a", "A")])],
        )
        schema = field_schema_verbose(field)
        self.assertEqual(
            schema["choices"],
            [{"value": "x", "label": "X"}, {"value": "a", "label": "A"}],
        )

    def test_malformed_choices_never_raise(self):
        # A 3-tuple entry would blow up the old unpack; defensively skipped now.
        field = _FakeField(name="bad", verbose_name="bad", choices=[("a", "A", "extra"), ("b", "B")])
        schema = field_schema_verbose(field)
        self.assertEqual(schema["choices"], [{"value": "b", "label": "B"}])

    def test_empty_choices_leave_base_value_list(self):
        # No choices -> the verbose helper adds nothing; the shared field_schema's
        # plain value-list (here empty) is left untouched, never a [{value,label}].
        field = _FakeField(name="none", verbose_name="none", choices=None)
        schema = field_schema_verbose(field)
        self.assertEqual(schema["choices"], [])

    def test_all_malformed_choices_leave_base_value_list(self):
        # If nothing flattens cleanly, the structured form is not applied and the
        # shared field_schema's value-list survives (defensive, never raises).
        field = _FakeField(name="allbad", verbose_name="allbad", choices=[("a", "A", "extra")])
        schema = field_schema_verbose(field)
        self.assertEqual(schema["choices"], ["a"])

    def test_malformed_inner_optgroup_entry_is_skipped(self):
        # An optgroup whose inner entry can't unpack to (value, label) is skipped,
        # while well-formed siblings in the same group still flatten cleanly.
        field = _FakeField(
            name="badinner",
            verbose_name="badinner",
            choices=[("Group", [("a", "A", "extra"), ("b", "B")])],
        )
        schema = field_schema_verbose(field)
        self.assertEqual(schema["choices"], [{"value": "b", "label": "B"}])

    def test_flatten_failure_is_swallowed(self):
        # If _flatten_choices itself raises (here a label whose str() explodes),
        # field_schema_verbose swallows it (never raises) and leaves the shared
        # field_schema's base value-list untouched.
        field = _FakeField(name="explode", verbose_name="explode", choices=[("a", _ExplodingLabel())])
        schema = field_schema_verbose(field)
        self.assertEqual(schema["choices"], ["a"])
