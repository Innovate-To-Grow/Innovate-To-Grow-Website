"""Shared setup for the Site Settings → Request Limits admin tests: a Core-app staff member, a fake request-limit
clock and a clean in-process limiter state."""

from django.conf import settings
from django.core.cache import cache
from django.forms import BooleanField
from django.test import TestCase
from django.urls import reverse

from apps.core.admin.request_limits.forms import RequestLimitPolicyForm
from apps.core.models import RequestRateLimitPolicy
from apps.core.tests.request_limits.helpers import isolate
from apps.event.tests.helpers import make_admin

URL = "/admin/core/request-limits/"
STATUS_URL = "/admin/core/request-limits/status/"


class RequestLimitsAdminTestCase(TestCase):
    """Signed in as a staff member who holds only the Core (System) app."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.clock = isolate(self)
        self.staff = make_admin(apps=["core"], email="corestaff@example.com")
        self.client.force_login(self.staff)
        self.url = reverse("admin:core_request_limits")
        self.status_url = reverse("admin:core_request_limits_status")

    def policy(self, scope):
        return RequestRateLimitPolicy.for_scope(scope)

    def set_policy(self, scope, **values):
        RequestRateLimitPolicy.objects.filter(pk=self.policy(scope).pk).update(**values)

    def post_data(self, **overrides):
        """The whole page as a browser posts it unchanged, with ``overrides`` (``None`` unticks a switch or drops a
        field)."""
        data = {}
        for scope in settings.REQUEST_RATE_LIMITS["scopes"]:
            form = RequestLimitPolicyForm(instance=self.policy(scope), prefix=scope)
            for name, field in form.fields.items():
                value = form[name].value()
                if isinstance(field, BooleanField):
                    if value:
                        data[form.add_prefix(name)] = "on"
                else:
                    data[form.add_prefix(name)] = "" if value is None else str(value)
        for key, value in overrides.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        return data

    def card_html(self, response, scope):
        content = response.content.decode()
        start = content.index(f'id="limit-card-{scope}"')
        return content[start : content.index("</article>", start)]

    def card(self, response, scope):
        for group in response.context["groups"]:
            for card in (*group["routes"], *group["views"]):
                if card.scope == scope:
                    return card
        raise AssertionError(f"No card for {scope}")
