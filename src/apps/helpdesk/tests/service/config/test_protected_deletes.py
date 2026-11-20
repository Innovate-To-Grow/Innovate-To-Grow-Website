"""Helpdesk → Assignment Groups and Categories: what tickets still use is switched off, not deleted.

A ticket's category and assignment group, and a category's default group, are protected (``on_delete=PROTECT``): the
admin's delete page, and the list's "Delete selected" action, show Django's "Cannot delete" page naming what uses
it, and nothing is deleted. A group or category nothing uses deletes as before (members and a manager do not keep a
group; a response template's category is only cleared)."""

from django.contrib.admin import helpers
from django.core.cache import cache
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from ....models import AssignmentGroup, ResponseTemplate, TicketCategory
from ...helpers import helpdesk_staff
from ...helpers.service import Status, new_ticket


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
        self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())

    def test_a_group_a_ticket_uses_is_not_deleted(self):
        group = AssignmentGroup.objects.create(name="Events")
        ticket = new_ticket(assignment_group=group)

        self.assertProtected(group, ticket.display_number)
        with self.assertRaises(ProtectedError):
            group.delete()

    def test_a_group_that_is_a_categorys_default_is_not_deleted(self):
        group = AssignmentGroup.objects.create(name="Events")
        TicketCategory.objects.create(name="Registration", default_group=group)

        self.assertProtected(group, "Registration")

    def test_a_category_a_ticket_uses_is_not_deleted(self):
        category = TicketCategory.objects.create(name="Registration")
        ticket = new_ticket(category=category)

        self.assertProtected(category, ticket.display_number)
        with self.assertRaises(ProtectedError):
            category.delete()

    def test_a_ticket_that_is_closed_still_keeps_them(self):
        group = AssignmentGroup.objects.create(name="Events")
        category = TicketCategory.objects.create(name="Registration")
        ticket = new_ticket(status=Status.CLOSED, assignment_group=group, category=category)

        self.assertProtected(group, ticket.display_number)
        self.assertProtected(category, ticket.display_number)

    def test_what_nothing_uses_deletes(self):
        group = AssignmentGroup.objects.create(name="Spare", manager=self.agent)
        group.members.add(self.agent)
        category = TicketCategory.objects.create(name="Old")
        template = ResponseTemplate.objects.create(name="Old answer", body="Hello", category=category)

        for obj in (group, category):
            with self.subTest(obj._meta.model_name):
                page, posted = self.delete(obj)
                self.assertEqual(page.context["protected"], [])
                self.assertEqual(posted.status_code, 302)
                self.assertFalse(type(obj).objects.filter(pk=obj.pk).exists())
        template.refresh_from_db()
        self.assertIsNone(template.category)

    def test_delete_selected_refuses_the_whole_selection_when_one_is_used(self):
        used = AssignmentGroup.objects.create(name="Events")
        spare = AssignmentGroup.objects.create(name="Spare")
        new_ticket(assignment_group=used)
        data = {
            "action": "delete_selected",
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(used.pk), str(spare.pk)],
            "post": "yes",
        }

        response = self.client.post(reverse("admin:helpdesk_assignmentgroup_changelist"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["title"], "Cannot delete Assignment Groups")
        self.assertEqual(set(AssignmentGroup.objects.values_list("name", flat=True)), {"Events", "Spare"})
