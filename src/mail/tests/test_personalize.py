from django.test import TestCase

from mail.services.personalize import personalize


class PersonalizeTest(TestCase):
    def test_basic_replacement(self):
        template = "Hello {{name}}, welcome to {{org}}!"
        context = {"name": "Alice", "org": "I2G"}
        self.assertEqual(personalize(template, context), "Hello Alice, welcome to I2G!")

    def test_spaced_placeholder(self):
        template = "Hello {{ name }}, welcome to {{ org }}!"
        context = {"name": "Bob", "org": "Club"}
        self.assertEqual(personalize(template, context), "Hello Bob, welcome to Club!")

    def test_mixed_spacing(self):
        template = "Hi {{name}} and {{ name }}!"
        context = {"name": "Carol"}
        self.assertEqual(personalize(template, context), "Hi Carol and Carol!")

    def test_unknown_placeholder_untouched(self):
        template = "Hi {{name}}, your code is {{code}}."
        context = {"name": "Dan"}
        self.assertEqual(personalize(template, context), "Hi Dan, your code is {{code}}.")

    def test_none_value_replaced_with_empty(self):
        template = "Hello {{name}}!"
        context = {"name": None}
        self.assertEqual(personalize(template, context), "Hello !")

    def test_empty_string_value(self):
        template = "Hello {{name}}!"
        context = {"name": ""}
        self.assertEqual(personalize(template, context), "Hello !")

    def test_empty_context(self):
        template = "No {{replacements}} here."
        self.assertEqual(personalize(template, {}), "No {{replacements}} here.")

    def test_empty_template(self):
        self.assertEqual(personalize("", {"key": "value"}), "")

    def test_multiple_occurrences(self):
        template = "{{x}} and {{x}} and {{ x }}"
        context = {"x": "Y"}
        self.assertEqual(personalize(template, context), "Y and Y and Y")

    def test_html_in_template_preserved(self):
        template = "<p>Hello {{name}}</p>"
        context = {"name": "Eve"}
        self.assertEqual(personalize(template, context), "<p>Hello Eve</p>")

    def test_special_chars_in_value(self):
        template = "Hello {{name}}!"
        context = {"name": "<script>alert('xss')</script>"}
        result = personalize(template, context)
        self.assertIn("<script>", result)
