"""Helpdesk → the sidebar entry lit for a ticket page: the view of the list it was opened from, which Django carries
in the page's ``_changelist_filters`` (the list's query, URL-encoded). "Everything" (mail=all) is the Queue, not
"Automated & Spam"."""

import uuid
from urllib.parse import urlencode

from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse

from config.settings.base.integrations.admin import navigation

from ...helpers import helpdesk_staff
from ...helpers.service import new_ticket

VIEWS = {
    "": ["Queue"],
    "mail=all": ["Queue"],
    "mail=all&status=any": ["Queue"],
    "status=done": ["Queue"],
    "assignee=me": ["My Tickets"],
    "group=mine": ["My Groups"],
    "group=mine&assignee=none": ["Unassigned"],
    "assignee=none": ["Unassigned"],
    "sla=breached": ["SLA Breached"],
    "mail=automated&status=any": ["Automated & Spam"],
}


class TicketPageSidebarTests(TestCase):
    def setUp(self):
        cache.clear()

    def active(self, path) -> list[str]:
        section = next(item for item in navigation.SIDEBAR["navigation"] if item["title"] == "Helpdesk")
        request = RequestFactory().get(path)
        return [item["title"] for item in section["items"] if callable(item.get("active")) and item["active"](request)]

    def test_a_ticket_page_lights_the_view_it_was_opened_from(self):
        page = f"/admin/helpdesk/ticket/{uuid.uuid4()}/change/"
        for filters, expected in VIEWS.items():
            with self.subTest(filters):
                self.assertEqual(self.active(f"{page}?{urlencode({'_changelist_filters': filters})}"), expected)
        self.assertEqual(self.active(page), ["Queue"])

    def test_the_list_itself_lights_the_same_entries(self):
        for query, expected in VIEWS.items():
            with self.subTest(query):
                self.assertEqual(self.active(f"/admin/helpdesk/ticket/?{query}"), expected)

    def test_the_lists_links_carry_the_view_to_the_ticket_page(self):
        self.client.force_login(helpdesk_staff())
        ticket = new_ticket()

        response = self.client.get(f"{reverse('admin:helpdesk_ticket_changelist')}?assignee=none")

        carried = urlencode({"_changelist_filters": "assignee=none"})
        link = f"{reverse('admin:helpdesk_ticket_change', args=[ticket.pk])}?{carried}"
        self.assertContains(response, f'href="{link}"')
        self.assertEqual(self.active(link), ["Unassigned"])
