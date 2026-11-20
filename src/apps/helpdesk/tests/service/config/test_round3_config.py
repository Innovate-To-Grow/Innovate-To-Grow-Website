"""Configuration pages after the second live check of the admin:

- the acknowledgement text may not use {agent_name} (no member of staff wrote it); a misspelt placeholder such as
  {requester name} or { subject } would be sent as typed, so it is refused there and in a response template, while
  braces around ordinary words stay text;
- a response template saved without touching its body (a browser posts it with CRLF line ends) records no body change;
- SLA Targets: Helpdesk staff see a target's durations with the reason only an I2G Master changes them; the list has
  no Created at column; the add page for the last missing priority offers no "Save and add another"."""

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from ....admin.intake.sla_targets import MASTER_ONLY
from ....models import HelpdeskSettings, ResponseTemplate, SLATarget
from ....services.outbound.compose import unknown_placeholders
from ...helpers import helpdesk_staff, make_superuser
from .test_sla_targets import ADD, readonly

ACK_USE = "Use {ticket} (and {requester_name} or {subject}, which lose any link)."
TEMPLATE_USE = "Use {ticket}, {requester_name}, {subject} or {agent_name}."


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class PlaceholderTests(TestCase):
    def setUp(self):
        cache.clear()

    def acknowledgement_errors(self, text) -> list[str]:
        row = HelpdeskSettings.objects.create()
        request = RequestFactory().post("/")
        request.user = make_superuser(email="master@example.com")
        form_class = admin.site._registry[HelpdeskSettings].get_form(request, row, change=True)
        return form_class({"acknowledgement_text": text}, instance=row).errors.get("acknowledgement_text", [])

    def test_agent_name_is_refused_in_the_acknowledgement(self):
        self.assertEqual(
            self.acknowledgement_errors("Hello, {agent_name} has {ticket}."),
            [f"Unknown placeholder: {{agent_name}}. {ACK_USE}"],
        )

    def test_a_misspelt_placeholder_is_refused_and_braced_words_stay_text(self):
        text = "Hello {requester name}, { subject } is {Ticket}: {see below}, {ticket}."

        self.assertEqual(unknown_placeholders(text), ["{ subject }", "{Ticket}", "{requester name}"])
        self.assertEqual(
            self.acknowledgement_errors("Dear {Requester-Name}, {see below}"),
            [f"Unknown placeholder: {{Requester-Name}}. {ACK_USE}"],
        )

    def test_a_response_template_refuses_a_misspelt_placeholder(self):
        self.client.force_login(helpdesk_staff())
        data = {"name": "Parking", "body": "Hello {requester name}, see below.", "is_active": "on", "order": "0"}

        response = self.client.post(reverse("admin:helpdesk_responsetemplate_add"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["adminform"].form.errors["body"],
            [f"Unknown placeholder: {{requester name}}. {TEMPLATE_USE}"],
        )
        self.assertFalse(ResponseTemplate.objects.exists())


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class TemplateBodyTests(TestCase):
    def test_an_untouched_body_posted_with_crlf_line_ends_is_no_change(self):
        cache.clear()
        self.client.force_login(helpdesk_staff())
        template = ResponseTemplate.objects.create(name="Parking", body="Hello {requester_name},\n\nLot B is open.")
        data = {"name": "Parking lot", "body": template.body.replace("\n", "\r\n"), "is_active": "on", "order": "0"}

        response = self.client.post(reverse("admin:helpdesk_responsetemplate_change", args=[template.pk]), data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogEntry.objects.get().get_change_message(), "Changed Name.")
        template.refresh_from_db()
        self.assertEqual((template.name, template.body), ("Parking lot", "Hello {requester_name},\n\nLot B is open."))


class SLATargetPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.changelist = reverse("admin:helpdesk_slatarget_changelist")

    def test_staff_see_the_durations_and_why_only_a_master_changes_them(self):
        self.client.force_login(helpdesk_staff())
        high = SLATarget.objects.get(priority="high")

        page = self.client.get(reverse("admin:helpdesk_slatarget_change", args=[high.pk]))

        shown = readonly(page)
        self.assertEqual((shown["response_display"], shown["resolution_display"]), ("4 h", "2 d"))
        self.assertContains(page, MASTER_ONLY)

    def test_the_list_has_no_created_at_column(self):
        for user in (helpdesk_staff(), make_superuser(email="master@example.com")):
            with self.subTest(superuser=user.is_superuser):
                self.client.force_login(user)
                columns = self.client.get(self.changelist).context["cl"].list_display
                self.assertNotIn("created_at", columns)
                self.assertIn("priority_label", columns)

    def test_the_last_missing_priority_offers_no_save_and_add_another(self):
        self.client.force_login(make_superuser(email="master@example.com"))
        SLATarget.objects.filter(priority__in=["urgent", "normal"]).delete()

        two_missing = self.client.get(reverse(ADD))
        SLATarget.objects.create(priority="urgent", response_minutes=60, resolution_minutes=480)
        last_missing = self.client.get(reverse(ADD))

        self.assertContains(two_missing, 'name="_addanother"')
        self.assertNotContains(last_missing, 'name="_addanother"')
        self.assertContains(last_missing, 'name="_save"')
