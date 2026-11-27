"""The ownership columns are deprecated, not dropped (I2G-HELPDESK-01): ``Ticket.assignee``, ``Ticket.assignment_group``,
``TicketCategory.default_group`` and ``HelpdeskSettings.notify_assignment`` are no longer editable, and migration 0007
changes Django's model state only (it runs no SQL). Their data stays through every change staff make, and Django
still knows the fields, so deleting a member who held tickets or sat in a group still clears those links."""

from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from ....models import AssignmentGroup, HelpdeskSettings, Ticket, TicketCategory
from ....services import tickets
from ...helpers import helpdesk_staff, make_admin
from ...tickets.test_tickets import new_ticket

DEPRECATED = (
    (Ticket, "assignee"),
    (Ticket, "assignment_group"),
    (TicketCategory, "default_group"),
    (HelpdeskSettings, "notify_assignment"),
)


class KeptDataTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.holder = make_admin(email="sam@example.com", first_name="Sam", last_name="Lead")
        self.group = AssignmentGroup.objects.create(name="Events", manager=self.holder)
        self.group.members.add(self.holder)
        self.ticket = new_ticket()
        Ticket.objects.filter(pk=self.ticket.pk).update(assignee=self.holder, assignment_group=self.group)

    def test_changes_staff_make_keep_the_old_assignment(self):
        tickets.update_ticket(self.ticket, actor=self.agent, status=Ticket.Status.OPEN, impact=1)
        tickets.resolve([Ticket.objects.get(pk=self.ticket.pk)], actor=self.agent, code="solved")

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Ticket.Status.RESOLVED)
        self.assertEqual((self.ticket.assignee, self.ticket.assignment_group), (self.holder, self.group))

    def test_deleting_a_member_who_held_tickets_and_sat_in_a_group_still_works(self):
        self.holder.delete()

        self.ticket.refresh_from_db()
        self.group.refresh_from_db()
        self.assertIsNone(self.ticket.assignee_id)
        self.assertEqual(self.ticket.assignment_group, self.group)
        self.assertIsNone(self.group.manager_id)
        self.assertFalse(self.group.members.exists())
        self.assertFalse(AssignmentGroup.members.through.objects.exists())


class DeprecatedFieldTests(TestCase):
    def test_the_deprecated_fields_are_not_editable(self):
        for model, name in DEPRECATED:
            with self.subTest(field=f"{model.__name__}.{name}"):
                field = model._meta.get_field(name)
                self.assertFalse(field.editable)
                self.assertTrue(field.help_text.startswith("Deprecated"))
                if name != "notify_assignment":
                    self.assertTrue(field.null)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_the_category_page_no_longer_offers_a_default_group(self):
        cache.clear()
        self.client.force_login(helpdesk_staff())
        category = TicketCategory.objects.create(name="Showcase")

        for url in (
            reverse("admin:helpdesk_ticketcategory_add"),
            reverse("admin:helpdesk_ticketcategory_change", args=[category.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("default_group", response.context["adminform"].form.fields)
        listed = self.client.get(reverse("admin:helpdesk_ticketcategory_changelist"))
        self.assertNotIn("default_group", listed.context["cl"].list_display)


class MigrationTests(TransactionTestCase):
    """Outside a test transaction: SQLite's schema editor cannot open inside one."""

    def test_migration_0007_runs_no_sql(self):
        out = StringIO()

        call_command("sqlmigrate", "helpdesk", "0007", stdout=out)

        statements = [
            line
            for line in out.getvalue().splitlines()
            if line.strip() and not line.startswith("--") and line.strip().upper() not in ("BEGIN;", "COMMIT;")
        ]
        self.assertEqual(statements, [])
