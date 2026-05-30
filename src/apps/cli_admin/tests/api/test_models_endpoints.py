from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff


class ReadEndpointTests(CliApiTestCase):
    def setUp(self):
        super().setUp()
        self.staff = make_staff(email="read@example.com", first_name="Reed", last_name="Staff")
        _, self.raw = issue_token(self.staff)

    def test_whoami(self):
        response = self.client.get("/admin-api/whoami/", **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["member_uuid"], str(self.staff.pk))
        self.assertEqual(response.data["email"], "read@example.com")
        self.assertTrue(response.data["is_staff"])
        self.assertTrue(response.data["is_active"])
        self.assertFalse(response.data["is_superuser"])
        self.assertIsNotNone(response.data["token_expires_at"])
        self.assertEqual(response.data["name"], "Reed Staff")

    def test_model_list_includes_writable_and_excludes_denied(self):
        response = self.client.get("/admin-api/models/", **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        labels = {row["label"]: row for row in response.data}
        self.assertIn("projects.Semester", labels)
        self.assertTrue(labels["projects.Semester"]["writable"])
        # Denied models never appear.
        self.assertNotIn("admin.LogEntry", labels)
        self.assertNotIn("cli_admin.CliAccessToken", labels)
        self.assertNotIn("sessions.Session", labels)

    def test_model_schema(self):
        response = self.client.get("/admin-api/models/projects/semester/schema/", **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["model"], "projects.Semester")
        self.assertEqual(response.data["primary_key"], "id")
        readable = {field["name"] for field in response.data["readable_fields"]}
        writable = {field["name"] for field in response.data["writable_fields"]}
        self.assertIn("year", readable)
        self.assertIn("season", writable)
        self.assertIn("is_published", writable)

    def test_model_schema_denied_is_400(self):
        response = self.client.get("/admin-api/models/admin/logentry/schema/", **self.auth(self.raw))
        self.assertEqual(response.status_code, 400)
