"""What a sync learns and carries to the next one: the trace permission from the token (never the stale roles of a
token cached before the grant), and the window length, halved after a window outran the request budget."""

import re
from datetime import datetime, timedelta
from urllib.parse import unquote

from django.test import TestCase

from apps.core.models import EmailDeliveryTraceState, OutboundEmail
from apps.core.services.email.graph.tracing import sync_delivery
from apps.core.services.email.graph.tracing.reader import GraphTraceReader
from apps.core.services.email.graph.tracing.state import state_for
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings

from . import SENDER, TraceSetupMixin, token_response, token_with_roles, trace_page, trace_row

DeliveryStatus = OutboundEmail.DeliveryStatus
Permission = EmailDeliveryTraceState.Permission
BOUNDS = re.compile(r"receivedDateTime ge (\S+) and receivedDateTime le ([^&]+)&")
WITHOUT_ROLE = ("Mail.Send", "Mail.ReadWrite")


def span(request) -> timedelta:
    start, end = BOUNDS.search(unquote(request["path"])).groups()
    return datetime.fromisoformat(end) - datetime.fromisoformat(start)


class PermissionTests(TraceSetupMixin, TestCase):
    def state(self):
        return EmailDeliveryTraceState.objects.get(sender=SENDER)

    def set_state(self, **values):
        state_for(SENDER)
        EmailDeliveryTraceState.objects.filter(sender=SENDER).update(**values)

    def cache_token(self, roles):
        self.microsoft.token = token_response(token=token_with_roles(roles))
        GraphTraceReader(self.config, SENDER).access_token()

    def test_a_token_with_the_role_ends_not_permitted_with_nothing_to_trace(self):
        self.set_state(permission=Permission.NOT_PERMITTED)

        outcome = sync_delivery()

        self.assertEqual((outcome.status, self.microsoft.traces), ("ok", []))
        self.assertEqual(self.state().permission, Permission.UNKNOWN)

    def test_with_nothing_to_trace_a_confirmed_permission_stays(self):
        self.set_state(permission=Permission.OK)

        self.assertEqual(sync_delivery().status, "ok")
        self.assertEqual(self.state().permission, Permission.OK)

    def test_a_token_cached_before_the_grant_is_replaced_before_judging(self):
        self.cache_token(WITHOUT_ROLE)
        self.microsoft.token = token_response(token=token_with_roles(("Mail.Send", "ExchangeMessageTrace.Read.All")))
        self.sent()

        outcome = sync_delivery()

        self.assertEqual((outcome.status, self.microsoft.tokens, len(self.microsoft.traces)), ("ok", 2, 1))
        self.assertEqual(self.state().permission, Permission.OK)

    def test_a_just_issued_token_without_the_role_is_not_permitted(self):
        self.cache_token(WITHOUT_ROLE)
        self.sent()

        outcome = sync_delivery()

        self.assertEqual((outcome.status, self.microsoft.tokens, self.microsoft.traces), ("not_permitted", 2, []))
        self.assertEqual(self.state().permission, Permission.NOT_PERMITTED)


class WindowLengthTests(TraceSetupMixin, TestCase):
    def sync(self, **settings_changes):
        EmailDeliveryTraceState.objects.update(next_run_after=None)
        with monitoring_settings(**settings_changes):
            return sync_delivery()

    def test_a_window_outrunning_the_budget_is_read_half_as_long_next_run(self):
        self.sent(hours_ago=30)
        self.microsoft.pages = [trace_page([trace_row(message_id="<other@x>")], skiptoken="more")]

        first = self.sync(trace_max_requests_per_run=2)
        second = self.sync(trace_max_requests_per_run=2)

        self.assertEqual((first.stats["window_minutes"], second.stats["window_minutes"]), (720, 360))
        hours = [span(request) / timedelta(hours=1) for request in self.microsoft.traces]
        self.assertEqual(hours, [24, 24, 12, 12])

    def test_a_shorter_window_read_in_full_infers_the_json_send_the_partial_one_could_not(self):
        json_sent = self.sent(hours_ago=30, internet_message_id="", subject="Your code")
        row = trace_row("<json@namprd.outlook.com>", subject="Your code", received=json_sent.accepted_at)
        self.microsoft.pages = [trace_page([row], skiptoken="more"), trace_page([row])]

        self.assertEqual(self.sync(trace_max_requests_per_run=1).status, "partial")
        json_sent.refresh_from_db()
        self.assertEqual(json_sent.delivery_status, DeliveryStatus.UNKNOWN)

        self.assertEqual(self.sync(trace_max_requests_per_run=1).status, "ok")
        json_sent.refresh_from_db()
        self.assertEqual(json_sent.delivery_status, DeliveryStatus.DELIVERED)

    def test_windows_fitting_with_room_to_spare_grow_back_never_under_an_hour(self):
        self.sent(hours_ago=30)
        state_for(SENDER)
        EmailDeliveryTraceState.objects.update(last_run_stats={"window_minutes": 1})

        outcome = self.sync()

        self.assertEqual(span(self.microsoft.traces[0]), timedelta(hours=1))
        self.assertEqual(outcome.stats["window_minutes"], 120)
        EmailDeliveryTraceState.objects.update(last_run_stats={"window_minutes": 24 * 60})
        self.assertEqual(self.sync().stats["window_minutes"], 24 * 60)
