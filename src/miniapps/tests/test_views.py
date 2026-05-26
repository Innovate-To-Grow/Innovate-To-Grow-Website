from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from miniapps.models import MiniApp, MiniAppDataRecord, MiniAppDataSchema

User = get_user_model()


class MiniAppCodeViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.app = MiniApp.objects.create(
            url_path="/code-test",
            title="Code Test",
            slug="code-test",
            status="published",
            html_code="<h1>Hello World</h1>",
            js_code="console.log('loaded');",
            css_code="h1 { color: blue; }",
        )

    def test_serves_published_app(self):
        response = self.client.get("/miniapps/code-test/code/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("<h1>Hello World</h1>", response.content.decode())
        self.assertIn("console.log('loaded');", response.content.decode())
        self.assertIn("h1 { color: blue; }", response.content.decode())
        self.assertIn("window.ITG", response.content.decode())

    def test_404_for_draft_app(self):
        self.app.status = "draft"
        self.app.save()
        response = self.client.get("/miniapps/code-test/code/")
        self.assertEqual(response.status_code, 404)

    def test_404_for_unknown_slug(self):
        response = self.client.get("/miniapps/nonexistent/code/")
        self.assertEqual(response.status_code, 404)

    def test_cors_header(self):
        response = self.client.get("/miniapps/code-test/code/")
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")


class MiniAppResolveViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        MiniApp.objects.create(url_path="/my-tool", title="My Tool", slug="my-tool", status="published")

    def test_resolves_published_app(self):
        response = self.client.get("/miniapps/resolve/", {"path": "/my-tool"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"slug": "my-tool", "title": "My Tool", "path": "/my-tool"})

    def test_404_for_unknown_path(self):
        response = self.client.get("/miniapps/resolve/", {"path": "/unknown"})
        self.assertEqual(response.status_code, 404)

    def test_400_without_path_param(self):
        response = self.client.get("/miniapps/resolve/")
        self.assertEqual(response.status_code, 400)


class MiniAppDataViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email="test@example.com", password="testpass")
        self.app = MiniApp.objects.create(
            url_path="/data-test", title="Data Test", slug="data-test", status="published"
        )
        MiniAppDataSchema.objects.create(
            app=self.app,
            fields=[
                {"name": "title", "type": "text", "required": True, "max_length": 100},
                {"name": "count", "type": "integer", "required": False},
            ],
        )

    def test_create_record(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/miniapps/data-test/data/",
            {"data": {"title": "Hello", "count": 5}},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["data"]["title"], "Hello")
        self.assertEqual(response.json()["data"]["count"], 5)

    def test_create_record_unauthenticated(self):
        response = self.client.post(
            "/miniapps/data-test/data/",
            {"data": {"title": "Hello"}},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_create_record_validation_error(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/miniapps/data-test/data/",
            {"data": {"count": 5}},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_list_records(self):
        MiniAppDataRecord.objects.create(app=self.app, data={"title": "One"})
        MiniAppDataRecord.objects.create(app=self.app, data={"title": "Two"})
        response = self.client.get("/miniapps/data-test/data/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)

    def test_get_record(self):
        record = MiniAppDataRecord.objects.create(app=self.app, data={"title": "Get Me"})
        response = self.client.get(f"/miniapps/data-test/data/{record.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["title"], "Get Me")

    def test_update_record(self):
        self.client.force_authenticate(user=self.user)
        record = MiniAppDataRecord.objects.create(app=self.app, data={"title": "Original"})
        response = self.client.patch(
            f"/miniapps/data-test/data/{record.pk}/",
            {"data": {"title": "Updated"}},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["title"], "Updated")

    def test_update_record_unauthenticated(self):
        record = MiniAppDataRecord.objects.create(app=self.app, data={"title": "Original"})
        response = self.client.patch(
            f"/miniapps/data-test/data/{record.pk}/",
            {"data": {"title": "Hacked"}},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_delete_record(self):
        self.client.force_authenticate(user=self.user)
        record = MiniAppDataRecord.objects.create(app=self.app, data={"title": "Delete Me"})
        response = self.client.delete(f"/miniapps/data-test/data/{record.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(MiniAppDataRecord.objects.filter(pk=record.pk).exists())

    def test_delete_record_unauthenticated(self):
        record = MiniAppDataRecord.objects.create(app=self.app, data={"title": "Safe"})
        response = self.client.delete(f"/miniapps/data-test/data/{record.pk}/")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(MiniAppDataRecord.objects.filter(pk=record.pk).exists())


class MiniAppSchemaViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.app = MiniApp.objects.create(
            url_path="/schema-view-test", title="Schema View", slug="schema-view-test", status="published"
        )

    def test_returns_empty_when_no_schema(self):
        response = self.client.get("/miniapps/schema-view-test/schema/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"fields": []})

    def test_returns_schema_fields(self):
        MiniAppDataSchema.objects.create(
            app=self.app,
            fields=[{"name": "email", "type": "email", "required": True}],
        )
        response = self.client.get("/miniapps/schema-view-test/schema/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["fields"]), 1)
        self.assertEqual(data["fields"][0]["name"], "email")
