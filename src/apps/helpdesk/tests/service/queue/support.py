"""What the queue tests share: a signed-in Helpdesk agent, the list as one of its views shows it, and a bulk action
posted from the list (with the list's query string, as the changelist form posts back to the view it shows)."""

from django.contrib.admin import helpers
from django.contrib.admin.models import LogEntry
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from ...helpers import helpdesk_staff

CHANGELIST = "admin:helpdesk_ticket_changelist"
ACTION_SESSION_KEY = "_admin_pending_action_helpdesk_ticket"
EVERYTHING = "?mail=all&status=any"


def history(ticket) -> list[str]:
    """The ticket's admin-history messages."""
    return list(LogEntry.objects.filter(object_id=str(ticket.pk)).values_list("change_message", flat=True))


class QueueCase(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)

    def get(self, query=""):
        response = self.client.get(f"{reverse(CHANGELIST)}?{query}")
        self.assertEqual(response.status_code, 200)
        return response

    def listed(self, query="") -> list[str]:
        """The subjects the list shows, in its order."""
        return [ticket.subject for ticket in self.get(query).context["cl"].result_list]

    def choices(self, title, query="") -> dict[str, bool]:
        """A filter's choices as the list shows them: their text, and whether each is the selected one."""
        changelist = self.get(query).context["cl"]
        spec = next(spec for spec in changelist.filter_specs if spec.title == title)
        return {str(choice["display"]): choice["selected"] for choice in spec.choices(changelist)}

    def act(self, action, *selected, view=EVERYTHING, follow=True, **data):
        data = {
            "action": action,
            "index": "0",
            "select_across": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(ticket.pk) for ticket in selected],
            **data,
        }
        return self.client.post(f"{reverse(CHANGELIST)}{view}", data, follow=follow)

    def messages(self, response) -> list[str]:
        return [str(message) for message in get_messages(response.wsgi_request)]
