"""Helpdesk → SLA Targets (``admin.intake.sla_targets``): every Admin sees and sets them.

The list is in order of severity. An Admin changes a target, and adds one only while a priority has no row, choosing
among the missing priorities; a member who is not an Admin is sent to the sign-in and changes nothing. A first
response may not be due after the resolution (``SLATarget.clean``). A saved target shows its priority's label
read-only, not a choice; durations read in days, hours and minutes."""

from django.contrib import admin
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_member

from ....admin.intake.sla_targets import _duration
from ....models import SLATarget
from ...helpers import helpdesk_staff

LATE_RESPONSE = "The first response cannot be due after the resolution."
ADD = "admin:helpdesk_slatarget_add"


def readonly(response) -> dict[str, str]:
    """The read-only rows of a change page: their name, and what they show."""
    return {
        field.field["name"]: str(field.contents())
        for fieldset in response.context["adminform"]
        for line in fieldset
        for field in line
        if field.is_readonly
    }


class _TargetCase(TestCase):
    def setUp(self):
        cache.clear()
        self.high = SLATarget.objects.get(priority="high")  # 4 h to respond, 2 days to resolve (the migration's)
        self.url = reverse("admin:helpdesk_slatarget_change", args=[self.high.pk])

    def post(self, response="120", resolution="1440", url=None, **values):
        data = {"response_minutes": response, "resolution_minutes": resolution, "is_active": "on", **values}
        return self.client.post(url or self.url, data)

    def assertTargetUnchanged(self):
        self.high.refresh_from_db()
        self.assertEqual((self.high.response_minutes, self.high.resolution_minutes), (240, 2880))


class AdminTests(_TargetCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(helpdesk_staff())

    def test_the_list_is_in_order_of_severity(self):
        response = self.client.get(reverse("admin:helpdesk_slatarget_changelist"))

        rows = response.context["cl"].result_list
        targets = admin.site._registry[SLATarget]
        self.assertEqual(
            [
                (targets.priority_label(row), targets.response_display(row), targets.resolution_display(row))
                for row in rows
            ],
            [
                ("1 – Critical", "1 h", "8 h"),
                ("2 – High", "4 h", "2 d"),
                ("3 – Moderate", "1 d", "5 d"),
                ("4 – Low", "3 d", "10 d"),
            ],
        )
        self.assertIsNotNone(response.context["cl"].formset)  # the Active boxes

    def test_an_admin_changes_a_target_whose_priority_stays_read_only(self):
        page = self.client.get(self.url)
        response = self.post(priority="urgent")  # the priority is no field once saved: a posted one is ignored

        form = page.context["adminform"].form
        self.assertEqual(list(form.fields), ["response_minutes", "resolution_minutes", "is_active"])
        self.assertEqual(readonly(page), {"priority_label": "2 – High"})
        self.assertIn("1440 = 1 day", form.fields["response_minutes"].help_text)
        self.assertEqual(response.status_code, 302)
        self.high.refresh_from_db()
        self.assertEqual(
            (self.high.priority, self.high.response_minutes, self.high.resolution_minutes), ("high", 120, 1440)
        )

    def test_the_response_cannot_be_due_after_the_resolution(self):
        late = self.post(response="3000", resolution="2000")

        self.assertEqual(late.status_code, 200)
        self.assertEqual(late.context["adminform"].form.errors["response_minutes"], [LATE_RESPONSE])
        self.assertTargetUnchanged()
        self.assertEqual(self.post(response="2000", resolution="2000").status_code, 302)  # the same time is fine

    def test_a_target_is_added_only_for_a_priority_without_one(self):
        self.assertEqual(self.client.get(reverse(ADD)).status_code, 403)  # every priority has its row
        SLATarget.objects.filter(priority__in=["urgent", "normal"]).delete()

        page = self.client.get(reverse(ADD))
        taken = self.post(url=reverse(ADD), priority="high")
        added = self.post(url=reverse(ADD), priority="urgent", response="30", resolution="240")

        self.assertEqual(
            dict(page.context["adminform"].form.fields["priority"].choices),
            {"normal": "3 – Moderate", "urgent": "1 – Critical"},
        )
        self.assertEqual(taken.status_code, 200)
        self.assertIn("priority", taken.context["adminform"].form.errors)
        self.assertEqual(SLATarget.objects.filter(priority="high").count(), 1)
        self.assertEqual(added.status_code, 302)
        self.assertEqual(SLATarget.objects.get(priority="urgent").response_minutes, 30)
        choices = self.client.get(reverse(ADD)).context["adminform"].form.fields["priority"].choices
        self.assertEqual(choices, [("normal", "3 – Moderate")])

    def test_an_added_target_is_judged_too(self):
        SLATarget.objects.filter(priority="low").delete()

        response = self.post(url=reverse(ADD), priority="low", response="600", resolution="599")

        self.assertEqual(response.context["adminform"].form.errors["response_minutes"], [LATE_RESPONSE])
        self.assertFalse(SLATarget.objects.filter(priority="low").exists())


class NotAnAdminTests(_TargetCase):
    def test_a_member_who_is_not_an_admin_changes_and_adds_nothing(self):
        self.client.force_login(make_member(email="member@example.com"))
        SLATarget.objects.filter(priority="low").delete()

        for response in (self.post(), self.client.get(reverse(ADD)), self.post(url=reverse(ADD), priority="low")):
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login/", response["Location"])
        self.assertTargetUnchanged()
        self.assertFalse(SLATarget.objects.filter(priority="low").exists())


class TargetRuleTests(TestCase):
    def test_clean_refuses_a_response_due_after_the_resolution(self):
        with self.assertRaises(ValidationError) as caught:
            SLATarget(priority="low", response_minutes=61, resolution_minutes=60).clean()

        self.assertEqual(caught.exception.message_dict, {"response_minutes": [LATE_RESPONSE]})
        SLATarget(priority="low", response_minutes=60, resolution_minutes=60).clean()
        SLATarget(priority="low", response_minutes=None, resolution_minutes=60).clean()  # the field reports a blank

    def test_durations_without_minutes_or_with_every_unit(self):
        cases = {None: "0 min", 59: "59 min", 1441: "1 d 1 min", 2 * 1440 + 3 * 60 + 4: "2 d 3 h 4 min", 14400: "10 d"}
        for minutes, label in cases.items():
            with self.subTest(minutes):
                self.assertEqual(_duration(minutes), label)
