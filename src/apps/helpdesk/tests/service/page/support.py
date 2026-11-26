"""What the ticket-page tests share: a signed-in Helpdesk agent, the page's form as the page showed it (each field's
value, and the hidden initial value Django renders beside each editable one), and posting that form back with some
fields edited, as a browser tab opened earlier would."""

import json
import re

from django.contrib import admin
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from ....models import Ticket
from ...helpers import helpdesk_staff


def change_url(ticket) -> str:
    return reverse("admin:helpdesk_ticket_change", args=[ticket.pk])


def ticket_admin():
    return admin.site._registry[Ticket]


class PageCase(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)

    def page(self, ticket):
        response = self.client.get(change_url(ticket))
        self.assertEqual(response.status_code, 200)
        return response

    def form(self, response):
        return response.context["adminform"].form

    def shown(self, ticket) -> dict[str, str]:
        """The ticket's form as its page shows it now: what the page posts back when nothing is edited."""
        form = self.form(self.page(ticket))
        data = {}
        for name, field in form.fields.items():
            value = form[name].value()
            data[name] = "" if value is None else str(value)
            if field.show_hidden_initial:
                data[form[name].html_initial_name] = data[name]
        return data

    def save(self, ticket, shown=None, **edits):
        """Post the page shown earlier (``shown``; by default the page as it is now) with ``edits`` typed into it."""
        data = dict(self.shown(ticket) if shown is None else shown)
        for name, value in edits.items():
            data[name] = "" if value is None else str(getattr(value, "pk", value))
        return self.client.post(change_url(ticket), data)

    def messages(self, response) -> list[str]:
        return [str(message) for message in get_messages(response.wsgi_request)]

    def json_script(self, response, element_id: str):
        """The data the page hands its script in ``<script id=… type="application/json">``."""
        found = re.search(
            rf'<script id="{element_id}" type="application/json">(.*?)</script>', response.content.decode()
        )
        self.assertIsNotNone(found, element_id)
        return json.loads(found.group(1))
