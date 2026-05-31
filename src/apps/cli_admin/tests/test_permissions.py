from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.cli_admin.permissions import IsActiveStaff
from apps.event.tests.helpers import make_member


class IsActiveStaffTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.perm = IsActiveStaff()

    def _check(self, user):
        request = self.factory.get("/admin-api/whoami/")
        request.user = user
        return self.perm.has_permission(request, view=None)

    def test_anonymous_denied(self):
        self.assertFalse(self._check(AnonymousUser()))

    def test_active_staff_allowed(self):
        self.assertTrue(self._check(make_member(email="s@example.com", is_staff=True)))

    def test_non_staff_denied(self):
        self.assertFalse(self._check(make_member(email="ns@example.com", is_staff=False)))

    def test_inactive_staff_denied(self):
        self.assertFalse(self._check(make_member(email="inact@example.com", is_staff=True, is_active=False)))
