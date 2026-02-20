from django.core.exceptions import ValidationError
from django.test import TestCase

from ...models import GoogleSheet, PageComponent, UniformForm


class ComponentTypeRestrictionTest(TestCase):
    """Test that component_type only allows supported values."""

    def test_valid_html_type(self):
        comp = PageComponent(name="C", component_type="html", html_content="<p/>")
        comp.full_clean()

    def test_valid_markdown_type(self):
        comp = PageComponent(name="C", component_type="markdown", html_content="<p/>")
        comp.full_clean()

    def test_valid_form_type(self):
        form = UniformForm.objects.create(name="Contact", slug="contact")
        comp = PageComponent(name="C", component_type="form", html_content="", form=form)
        comp.full_clean()

    def test_valid_table_type(self):
        comp = PageComponent(name="C", component_type="table", html_content="<table/>")
        comp.full_clean()

    def test_valid_google_sheet_type(self):
        google_sheet = GoogleSheet.objects.create(
            name="Public Schedule",
            spreadsheet_id="spreadsheet-id",
            sheet_name="Sheet1",
        )
        comp = PageComponent(
            name="C",
            component_type="google_sheet",
            google_sheet=google_sheet,
        )
        comp.full_clean()

    def test_invalid_template_type_rejected(self):
        """The old 'template' type should be rejected by validation."""
        comp = PageComponent(name="C", component_type="template", html_content="<p/>")
        with self.assertRaises(ValidationError):
            comp.full_clean()

    def test_invalid_widget_type_rejected(self):
        """The old 'widget' type should be rejected by validation."""
        comp = PageComponent(name="C", component_type="widget", html_content="<p/>")
        with self.assertRaises(ValidationError):
            comp.full_clean()


class GoogleSheetComponentValidationTest(TestCase):
    def setUp(self):
        self.google_sheet = GoogleSheet.objects.create(
            name="Shared Sheet",
            spreadsheet_id="spreadsheet-id",
            sheet_name="Sheet1",
        )

    def test_google_sheet_component_requires_google_sheet_fk(self):
        comp = PageComponent(name="C", component_type="google_sheet")
        with self.assertRaises(ValidationError):
            comp.full_clean()

    def test_non_google_sheet_component_cannot_set_google_sheet_fk(self):
        comp = PageComponent(
            name="C",
            component_type="html",
            html_content="<p/>",
            google_sheet=self.google_sheet,
        )
        with self.assertRaises(ValidationError):
            comp.full_clean()

    def test_google_sheet_component_rejects_disabled_google_sheet(self):
        self.google_sheet.is_enabled = False
        self.google_sheet.save(update_fields=["is_enabled", "updated_at"])

        comp = PageComponent(
            name="C",
            component_type="google_sheet",
            google_sheet=self.google_sheet,
        )
        with self.assertRaises(ValidationError):
            comp.full_clean()
