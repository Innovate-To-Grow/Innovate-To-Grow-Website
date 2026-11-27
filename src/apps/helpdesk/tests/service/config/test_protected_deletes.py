"""Helpdesk → Categories: what tickets still use is switched off, not deleted.

A ticket's category is protected (``on_delete=PROTECT``): the admin's delete page, and the list's "Delete selected"
action, show Django's "Cannot delete" page naming what uses it (with the advice to switch it off, never a note that
the user may not delete tickets), and nothing is deleted. A category nothing uses deletes as before (a response
template's category is only cleared). The deprecated assignment groups (I2G-HELPDESK-01) have no admin page, and
the database still refuses to delete one a ticket or a category still names: their data is kept."""

from django.contrib.admin import helpers
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from ....models import AssignmentGroup, ResponseTemplate, TicketCategory
from ...helpers import helpdesk_staff
from ...helpers.service import Status, new_ticket

IN_USE = (
    "Still in use (listed below), so it cannot be deleted. Switch it off instead (Is active): it stays on those "
    "tickets and is no longer offered."
)


class ProtectedDeleteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)

    def delete(self, obj):
        """The admin's delete page for ``obj``, and its "Yes, I'm sure" posted."""
        url = reverse(f"admin:helpdesk_{obj._meta.model_name}_delete", args=[obj.pk])
        return self.client.get(url), self.client.post(url, {"post": "yes"})

    def assertProtected(self, obj, used_by: str):
        for response in self.delete(obj):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["title"], f"Cannot delete {obj._meta.verbose_name}")
            self.assertEqual(len(response.context["protected"]), 1)
            self.assertIn(used_by, response.context["protected"][0])
            # Nothing would be deleted: no "your account doesn't have permission to delete tickets" instead.
            self.assertFalse(response.context["perms_lacking"])
            self.assertEqual([str(m) for m in get_messages(response.wsgi_request)], [IN_USE])
        self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())

    def test_a_deprecated_group_tickets_or_categories_still_name_is_kept(self):
        group = AssignmentGroup.objects.create(name="Events")
        new_ticket(status=Status.CLOSED, assignment_group=group)
        default = AssignmentGroup.objects.create(name="Registration desk")
        TicketCategory.objects.create(name="Registration", default_group=default)

        for kept in (group, default):
            with self.subTest(kept.name), self.assertRaises(ProtectedError):
                kept.delete()

    def test_a_category_a_ticket_uses_is_not_deleted(self):
        category = TicketCategory.objects.create(name="Registration")
        ticket = new_ticket(category=category)

        self.assertProtected(category, ticket.display_number)
        with self.assertRaises(ProtectedError):
            category.delete()

    def test_a_ticket_that_is_closed_still_keeps_it(self):
        category = TicketCategory.objects.create(name="Registration")
        ticket = new_ticket(status=Status.CLOSED, category=category)

        self.assertProtected(category, ticket.display_number)

    def test_what_nothing_uses_deletes(self):
        category = TicketCategory.objects.create(name="Old")
        template = ResponseTemplate.objects.create(name="Old answer", body="Hello", category=category)

        page, posted = self.delete(category)

        self.assertEqual(page.context["protected"], [])
        self.assertEqual(posted.status_code, 302)
        self.assertFalse(TicketCategory.objects.filter(pk=category.pk).exists())
        template.refresh_from_db()
        self.assertIsNone(template.category)

    def test_delete_selected_refuses_the_whole_selection_when_one_is_used(self):
        used = TicketCategory.objects.create(name="Events")
        spare = TicketCategory.objects.create(name="Spare")
        new_ticket(category=used)
        data = {
            "action": "delete_selected",
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(used.pk), str(spare.pk)],
            "post": "yes",
        }

        response = self.client.post(reverse("admin:helpdesk_ticketcategory_changelist"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["title"], "Cannot delete Ticket Categories")
        self.assertEqual(set(TicketCategory.objects.values_list("name", flat=True)), {"Events", "Spare"})
