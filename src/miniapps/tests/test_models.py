from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from miniapps.models import MiniApp, MiniAppDataRecord, MiniAppDataSchema, MiniAppVersion


class MiniAppModelTests(TestCase):
    def test_create_miniapp(self):
        app = MiniApp.objects.create(
            url_path="/test-app",
            title="Test App",
            slug="test-app",
            status="published",
            html_code="<h1>Hello</h1>",
            js_code="console.log('hi');",
            css_code="h1 { color: red; }",
        )
        self.assertEqual(str(app), "Test App (/test-app)")
        self.assertTrue(app.embeddable)

    def test_url_path_validation_requires_leading_slash(self):
        app = MiniApp(url_path="no-slash", title="Bad", slug="bad")
        with self.assertRaises(ValidationError):
            app.full_clean()

    def test_url_path_validation_rejects_uppercase(self):
        app = MiniApp(url_path="/UpperCase", title="Bad", slug="bad2")
        with self.assertRaises(ValidationError):
            app.full_clean()

    def test_slug_uniqueness(self):
        MiniApp.objects.create(url_path="/app-one", title="App One", slug="app-one")
        with self.assertRaises(IntegrityError):
            MiniApp.objects.create(url_path="/app-two", title="App Two", slug="app-one")


class MiniAppDataSchemaTests(TestCase):
    def setUp(self):
        self.app = MiniApp.objects.create(url_path="/schema-test", title="Schema Test", slug="schema-test")

    def test_create_schema(self):
        schema = MiniAppDataSchema.objects.create(
            app=self.app,
            fields=[
                {"name": "title", "type": "text", "required": True, "max_length": 200},
                {"name": "count", "type": "integer", "required": False},
            ],
        )
        self.assertEqual(str(schema), "Schema for Schema Test (2 fields)")


class MiniAppDataRecordTests(TestCase):
    def setUp(self):
        self.app = MiniApp.objects.create(url_path="/record-test", title="Record Test", slug="record-test")

    def test_create_record(self):
        record = MiniAppDataRecord.objects.create(app=self.app, data={"title": "Hello", "count": 5})
        self.assertEqual(record.data["title"], "Hello")
        self.assertIn("Record", str(record))


class MiniAppVersionTests(TestCase):
    def setUp(self):
        self.app = MiniApp.objects.create(url_path="/version-test", title="Version Test", slug="version-test")

    def test_create_version(self):
        v = MiniAppVersion.objects.create(
            app=self.app, version_number=1, html_code="<p>v1</p>", js_code="", css_code=""
        )
        self.assertEqual(str(v), "Version Test v1")

    def test_version_uniqueness(self):
        MiniAppVersion.objects.create(app=self.app, version_number=1, html_code="", js_code="", css_code="")
        with self.assertRaises(IntegrityError):
            MiniAppVersion.objects.create(app=self.app, version_number=1, html_code="", js_code="", css_code="")
