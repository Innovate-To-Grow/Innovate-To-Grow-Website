from django.apps import apps as django_apps

from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff
from apps.cli_admin.views.models import _is_cli_denied


class AppListEndpointTests(CliApiTestCase):
    def setUp(self):
        super().setUp()
        self.staff = make_staff(email="apps@example.com")
        _, self.raw = issue_token(self.staff)

    def test_app_list_returns_reachable_apps(self):
        response = self.client.get("/admin-api/apps/", **self.auth(self.raw))
        self.assertEqual(response.status_code, 200)
        labels = {row["app_label"] for row in response.data}
        # An app with reachable models appears.
        self.assertIn("projects", labels)
        # Every row carries an app_label and a positive model_count.
        for row in response.data:
            self.assertIn("app_label", row)
            self.assertIn("model_count", row)
            self.assertGreater(row["model_count"], 0)

    def test_app_list_excludes_fully_denied_apps(self):
        response = self.client.get("/admin-api/apps/", **self.auth(self.raw))
        labels = {row["app_label"] for row in response.data}
        # The whole authn app is denied; it has no reachable models.
        self.assertNotIn("authn", labels)
        # The cli_admin app's own models are all denied too.
        self.assertNotIn("cli_admin", labels)

    def test_app_list_is_sorted_by_app_label(self):
        response = self.client.get("/admin-api/apps/", **self.auth(self.raw))
        labels = [row["app_label"] for row in response.data]
        self.assertEqual(labels, sorted(labels))

    def test_model_counts_match_reachable_models(self):
        response = self.client.get("/admin-api/apps/", **self.auth(self.raw))
        rows = {row["app_label"]: row["model_count"] for row in response.data}
        expected = {}
        for model in django_apps.get_models():
            if _is_cli_denied(model, write=False):
                continue
            expected[model._meta.app_label] = expected.get(model._meta.app_label, 0) + 1
        self.assertEqual(rows, expected)

    def test_app_list_requires_auth(self):
        response = self.client.get("/admin-api/apps/")
        self.assertEqual(response.status_code, 401)
