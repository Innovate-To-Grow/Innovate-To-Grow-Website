"""The ticket form's ServiceNow rules (a resolution code to resolve or close; the assignee within the group), the
queue's Group and SLA filters and columns, and the configuration admins (groups, SLA targets, response templates)."""

from datetime import timedelta

from django.contrib import admin
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ...admin.intake.settings import _duration
from ...admin.tickets.filters import _DefaultChoiceFilter
from ...models import AssignmentGroup, ResponseTemplate, SLATarget, Ticket
from ..helpers import helpdesk_staff, make_admin
from .support import Status, clocked_ticket, new_ticket

HOUR = timedelta(hours=1)


class TicketFormTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.other = make_admin(apps=["helpdesk"], email="kim@example.com", first_name="Kim", last_name="Lee")
        self.client.force_login(self.agent)
        self.ticket = new_ticket(status=Status.OPEN)
        self.url = reverse("admin:helpdesk_ticket_change", args=[self.ticket.pk])

    def save(self, **values):
        data = {"status": Status.OPEN, "impact": "2", "urgency": "2", "category": "", "assignment_group": ""}
        data.update({key: str(value.pk) if hasattr(value, "pk") else value for key, value in values.items()})
        return self.client.post(self.url, data)

    def errors(self, response):
        return response.context["adminform"].form.errors

    def test_resolving_or_closing_needs_a_resolution_code(self):
        for status in (Status.RESOLVED, Status.CLOSED):
            with self.subTest(status):
                response = self.save(status=status)
                self.assertEqual(response.status_code, 200)
                self.assertIn("Choose a resolution code", str(self.errors(response)["resolution_code"]))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Status.OPEN)

    def test_with_a_code_and_notes_it_resolves(self):
        response = self.save(status=Status.RESOLVED, resolution_code="solved", resolution_notes="Answered by phone.")

        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(
            (self.ticket.status, self.ticket.resolution_code, self.ticket.resolution_notes),
            (Status.RESOLVED, "solved", "Answered by phone."),
        )

    def test_a_ticket_already_resolved_saves_without_a_code(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(status=Status.RESOLVED)

        self.assertEqual(self.save(status=Status.RESOLVED, impact="1").status_code, 302)

    def test_the_assignee_must_be_a_member_of_a_group_with_members(self):
        group = AssignmentGroup.objects.create(name="Events")
        group.members.add(self.other)

        refused = self.save(assignment_group=group, assignee=self.agent)
        accepted = self.save(assignment_group=group, assignee=self.other)

        self.assertIn("Avery Agent", str(self.errors(refused)["assignee"]))
        self.assertIn("is not a member of Events", str(self.errors(refused)["assignee"]))
        self.assertEqual(accepted.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.assignment_group, self.ticket.assignee), (group, self.other))

    def test_a_group_without_members_takes_anyone(self):
        group = AssignmentGroup.objects.create(name="Nobody yet")

        self.assertEqual(self.save(assignment_group=group, assignee=self.agent).status_code, 302)

    def test_an_unchanged_pair_is_not_judged_again(self):
        group = AssignmentGroup.objects.create(name="Events")
        Ticket.objects.filter(pk=self.ticket.pk).update(assignment_group=group, assignee=self.agent)
        group.members.add(self.other)  # the assignee is not (or no longer) a member

        response = self.save(assignment_group=group, assignee=self.agent, impact="1")

        self.assertEqual(response.status_code, 302)

    def test_a_form_without_impact_or_urgency_keeps_the_tickets(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(impact=1, urgency=1, priority="urgent")

        response = self.client.post(self.url, {"status": Status.PENDING_INTERNAL, "category": "", "assignee": ""})

        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(
            (self.ticket.status, self.ticket.impact, self.ticket.priority), ("pending_internal", 1, "urgent")
        )

    def test_only_active_groups_are_offered(self):
        AssignmentGroup.objects.create(name="Events")
        AssignmentGroup.objects.create(name="Retired", is_active=False)

        field = self.client.get(self.url).context["adminform"].form.fields["assignment_group"]

        self.assertEqual([group.name for group in field.queryset], ["Events"])


class QueueFilterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)
        self.mine = AssignmentGroup.objects.create(name="Events")
        self.mine.members.add(self.agent)
        self.theirs = AssignmentGroup.objects.create(name="Technical")
        now = timezone.now()
        new_ticket(subject="mine", assignment_group=self.mine)
        new_ticket(subject="theirs", assignment_group=self.theirs)
        new_ticket(subject="no group")
        new_ticket(subject="breached", sla_started_at=now - 3 * HOUR, response_due_at=now - HOUR)
        new_ticket(subject="due soon", sla_started_at=now - HOUR, response_due_at=now + 2 * HOUR)
        clocked_ticket(subject="on track", priority=Ticket.Priority.LOW)

    def listed(self, query):
        response = self.client.get(f"{reverse('admin:helpdesk_ticket_changelist')}?{query}")
        self.assertEqual(response.status_code, 200)
        return {ticket.subject for ticket in response.context["cl"].result_list}

    def test_group_filter(self):
        self.assertEqual(self.listed("group=mine"), {"mine"})
        self.assertEqual(self.listed(f"group={self.theirs.pk}"), {"theirs"})
        self.assertEqual(self.listed("group=none"), {"no group", "breached", "due soon", "on track"})
        self.assertEqual(self.listed("group=not-a-uuid"), set())

    def test_sla_filter(self):
        self.assertEqual(self.listed("sla=breached"), {"breached"})
        self.assertEqual(self.listed("sla=due_soon"), {"due soon"})
        self.assertEqual(self.listed("sla=none"), {"mine", "theirs", "no group"})
        self.assertEqual(len(self.listed("")), 6)  # no SLA choice: every open ticket

    def test_a_default_choice_filter_must_name_its_default(self):
        with self.assertRaises(NotImplementedError):
            _DefaultChoiceFilter.default_value(None)

    def test_the_group_and_sla_columns(self):
        response = self.client.get(reverse("admin:helpdesk_ticket_changelist"))

        self.assertContains(response, "Technical")
        self.assertContains(response, "Response: Breached")
        self.assertContains(response, "Response due ")


class SLAColumnTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = admin.site._registry[Ticket]

    def test_the_states_the_column_shows(self):
        now = timezone.now()
        self.assertEqual(self.admin.sla_column(new_ticket()), ("none", "—"))
        self.assertEqual(self.admin.sla_column(clocked_ticket(started=now - 30 * HOUR))[0], "breached")
        state, text = self.admin.sla_column(clocked_ticket(started=now - 20 * HOUR))
        self.assertEqual(state, "at_risk")
        self.assertTrue(text.startswith("Response due "))
        resolved = clocked_ticket(status=Status.RESOLVED, first_responded_at=now)
        self.assertEqual(self.admin.sla_column(resolved), ("met", "Resolution: Met"))
        self.assertEqual(self.admin.group_column(new_ticket()), "—")


class ConfigAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)

    def test_assignment_groups_list_and_add(self):
        group = AssignmentGroup.objects.create(name="Events", description="Showcase questions")
        group.members.add(self.agent)
        make_admin(apps=["event"], email="events@example.com")

        listing = self.client.get(reverse("admin:helpdesk_assignmentgroup_changelist"))
        add = self.client.get(reverse("admin:helpdesk_assignmentgroup_add"))

        self.assertContains(listing, "Showcase questions")
        self.assertEqual(listing.context["cl"].result_list[0].member_total, 1)
        self.assertEqual(add.status_code, 200)
        members = add.context["adminform"].form.fields["members"].queryset
        self.assertEqual(list(members), [self.agent])  # only staff with the Helpdesk app

    def test_sla_targets_list_change_and_cannot_be_deleted(self):
        target = SLATarget.objects.get(priority="urgent")

        listing = self.client.get(reverse("admin:helpdesk_slatarget_changelist"))
        change = self.client.get(reverse("admin:helpdesk_slatarget_change", args=[target.pk]))
        delete = self.client.get(reverse("admin:helpdesk_slatarget_delete", args=[target.pk]))

        self.assertContains(listing, "1 – Critical")
        self.assertContains(listing, "8 h")
        self.assertEqual(change.status_code, 200)
        self.assertNotIn("priority", change.context["adminform"].form.fields)  # read-only once saved
        self.assertEqual(delete.status_code, 403)
        self.assertTrue(SLATarget.objects.filter(pk=target.pk).exists())
        self.assertEqual(str(target), "SLA for 1 – Critical")

    def test_a_new_sla_target_picks_its_priority_from_the_list(self):
        SLATarget.objects.filter(priority="low").delete()

        add = self.client.get(reverse("admin:helpdesk_slatarget_add"))
        response = self.client.post(
            reverse("admin:helpdesk_slatarget_add"),
            {"priority": "low", "response_minutes": "90", "resolution_minutes": "1500", "is_active": "on"},
        )

        self.assertEqual(add.context["adminform"].form.fields["priority"].choices, Ticket.Priority.choices)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SLATarget.objects.get(priority="low").response_minutes, 90)

    def test_response_templates_list_and_add(self):
        template = ResponseTemplate.objects.create(name="Showcase time", body="It starts at 10.")
        self.assertEqual(str(template), "Showcase time")

        self.assertContains(self.client.get(reverse("admin:helpdesk_responsetemplate_changelist")), "Showcase time")
        self.assertEqual(self.client.get(reverse("admin:helpdesk_responsetemplate_add")).status_code, 200)

    def test_durations_read_in_days_hours_and_minutes(self):
        cases = {0: "0 min", 45: "45 min", 60: "1 h", 90: "1 h 30 min", 1440: "1 d", 1500: "1 d 1 h", 4321: "3 d 1 min"}
        for minutes, label in cases.items():
            with self.subTest(minutes):
                self.assertEqual(_duration(minutes), label)
