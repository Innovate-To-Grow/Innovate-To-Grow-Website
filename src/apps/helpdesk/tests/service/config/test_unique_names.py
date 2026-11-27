"""Names of categories and response templates are unique whatever their case ("front DESK" beside
"Front desk" is refused) and saved with their spaces tidied; a row may keep, or recase, its own name. A response
template uses only the four placeholders ({ticket}, {requester_name}, {subject}, {agent_name}): any other {word} would
be sent as typed, so it is refused; braces around words with spaces are plain text. Its body is stored with LF line
ends."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from ....models import ResponseTemplate, TicketCategory
from ...helpers import helpdesk_staff

MODELS = {"ticketcategory": TicketCategory, "responsetemplate": ResponseTemplate}
USE = "Use {ticket}, {requester_name}, {subject} or {agent_name}."


class _ConfigFormCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(helpdesk_staff())

    def save(self, model: str, obj=None, **values):
        """Post the add form of ``model`` (or the change form of ``obj``); fields a model lacks are ignored."""
        data = {"name": "Help line", "description": "", "body": "Hello", "is_active": "on", "order": "0", **values}
        if obj is None:
            return self.client.post(reverse(f"admin:helpdesk_{model}_add"), data)
        return self.client.post(reverse(f"admin:helpdesk_{model}_change", args=[obj.pk]), data)

    def errors(self, response, field: str) -> list[str]:
        self.assertEqual(response.status_code, 200)
        return list(response.context["adminform"].form.errors.get(field, []))


class UniqueNameTests(_ConfigFormCase):
    def setUp(self):
        super().setUp()
        self.existing = {model: cls.objects.create(name="Front desk") for model, cls in MODELS.items()}

    def test_a_name_taken_in_another_case_is_refused(self):
        for model, cls in MODELS.items():
            with self.subTest(model):
                response = self.save(model, name="  front   DESK ")

                self.assertEqual(
                    self.errors(response, "name"),
                    ["“front DESK” is taken already (names are compared whatever their case)."],
                )
                self.assertEqual(cls.objects.count(), 1)

    def test_spaces_are_tidied(self):
        for model, cls in MODELS.items():
            with self.subTest(model):
                self.assertEqual(self.save(model, name="  Help \t  line  ").status_code, 302)
                self.assertTrue(cls.objects.filter(name="Help line").exists())

    def test_a_row_keeps_or_recases_its_own_name(self):
        for model, obj in self.existing.items():
            with self.subTest(model):
                self.assertEqual(self.save(model, obj, name="Front desk").status_code, 302)
                self.assertEqual(self.save(model, obj, name="FRONT DESK").status_code, 302)
                obj.refresh_from_db()
                self.assertEqual(obj.name, "FRONT DESK")

    def test_another_rows_name_is_refused_on_a_change_too(self):
        other = TicketCategory.objects.create(name="Events")

        response = self.save("ticketcategory", other, name="FRONT desk")

        self.assertEqual(len(self.errors(response, "name")), 1)
        other.refresh_from_db()
        self.assertEqual(other.name, "Events")


class TemplatePlaceholderTests(_ConfigFormCase):
    def test_an_unknown_placeholder_is_refused(self):
        response = self.save("responsetemplate", body="Dear {first_name}, about {ticket}")

        self.assertEqual(self.errors(response, "body"), [f"Unknown placeholder: {{first_name}}. {USE}"])
        self.assertFalse(ResponseTemplate.objects.exists())

    def test_several_are_listed_once_each_in_order(self):
        response = self.save("responsetemplate", body="{name} {link} {name}")

        self.assertEqual(self.errors(response, "body"), [f"Unknown placeholders: {{link}}, {{name}}. {USE}"])

    def test_the_four_placeholders_and_plain_braces_are_accepted_and_stored_with_lf(self):
        body = "Hello {requester_name},\r\n\r\n{ticket} ({subject}) is with {agent_name}. {see the schedule}"

        response = self.save("responsetemplate", body=body)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ResponseTemplate.objects.get().body, body.replace("\r\n", "\n"))

    def test_a_change_is_judged_too(self):
        template = ResponseTemplate.objects.create(name="Parking", body="Lot {ticket}")

        response = self.save("responsetemplate", template, name="Parking", body="Lot {lot_number}")

        self.assertEqual(self.errors(response, "body"), [f"Unknown placeholder: {{lot_number}}. {USE}"])
        template.refresh_from_db()
        self.assertEqual(template.body, "Lot {ticket}")
