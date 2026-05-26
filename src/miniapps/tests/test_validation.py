from django.test import TestCase
from rest_framework.exceptions import ValidationError

from miniapps.models import MiniApp, MiniAppDataSchema
from miniapps.services.validation import validate_record_data


class ValidationServiceTests(TestCase):
    def setUp(self):
        self.app = MiniApp.objects.create(url_path="/val-test", title="Val Test", slug="val-test")
        self.schema = MiniAppDataSchema.objects.create(
            app=self.app,
            fields=[
                {"name": "name", "type": "text", "required": True, "max_length": 50},
                {"name": "age", "type": "integer", "required": False},
                {"name": "active", "type": "boolean", "required": False},
                {"name": "email", "type": "email", "required": False},
                {"name": "website", "type": "url", "required": False},
                {"name": "born", "type": "date", "required": False},
                {"name": "score", "type": "float", "required": False},
                {"name": "metadata", "type": "json", "required": False},
            ],
        )

    def test_valid_data(self):
        data = {"name": "Alice", "age": "30", "active": "true", "email": "a@b.com"}
        result = validate_record_data(self.schema, data)
        self.assertEqual(result["name"], "Alice")
        self.assertEqual(result["age"], 30)
        self.assertTrue(result["active"])

    def test_required_field_missing(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_record_data(self.schema, {"age": 25})
        self.assertIn("name", ctx.exception.detail)

    def test_max_length_exceeded(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_record_data(self.schema, {"name": "x" * 51})
        self.assertIn("name", ctx.exception.detail)

    def test_invalid_integer(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_record_data(self.schema, {"name": "Bob", "age": "abc"})
        self.assertIn("age", ctx.exception.detail)

    def test_invalid_email(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_record_data(self.schema, {"name": "Bob", "email": "notanemail"})
        self.assertIn("email", ctx.exception.detail)

    def test_invalid_url(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_record_data(self.schema, {"name": "Bob", "website": "notaurl"})
        self.assertIn("website", ctx.exception.detail)

    def test_valid_url(self):
        result = validate_record_data(self.schema, {"name": "Bob", "website": "https://example.com"})
        self.assertEqual(result["website"], "https://example.com")

    def test_boolean_coercion(self):
        result = validate_record_data(self.schema, {"name": "X", "active": "false"})
        self.assertFalse(result["active"])

    def test_date_validation(self):
        result = validate_record_data(self.schema, {"name": "X", "born": "2000-01-15"})
        self.assertEqual(result["born"], "2000-01-15")

    def test_invalid_date(self):
        with self.assertRaises(ValidationError):
            validate_record_data(self.schema, {"name": "X", "born": "not-a-date"})

    def test_float_coercion(self):
        result = validate_record_data(self.schema, {"name": "X", "score": "3.14"})
        self.assertAlmostEqual(result["score"], 3.14)

    def test_json_passthrough(self):
        result = validate_record_data(self.schema, {"name": "X", "metadata": {"foo": "bar"}})
        self.assertEqual(result["metadata"], {"foo": "bar"})

    def test_no_schema_passes_data_through(self):
        result = validate_record_data(None, {"anything": "goes"})
        self.assertEqual(result, {"anything": "goes"})

    def test_extra_fields_preserved(self):
        result = validate_record_data(self.schema, {"name": "Alice", "extra": "data"})
        self.assertEqual(result["extra"], "data")
