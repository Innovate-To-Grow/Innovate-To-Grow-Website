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
