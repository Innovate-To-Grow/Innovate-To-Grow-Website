"""Tests for the admin access predicate (apps.core.utils.access): an Admin is an authenticated, active staff member."""

from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, TestCase

from apps.core.utils.access import user_can_access_app, user_is_admin
from apps.event.tests.helpers import make_admin, make_member

APP_LABELS = ("cms", "event", "projects", "authn", "mail", "core", "admin", "cli_admin")


def _user(**kwargs):
    defaults = {"is_authenticated": True, "is_active": True, "is_staff": True, "is_superuser": False}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class UserIsAdminTest(SimpleTestCase):
    def test_active_staff_is_an_admin(self):
        self.assertTrue(user_is_admin(_user()))

    def test_none_is_not_an_admin(self):
        self.assertFalse(user_is_admin(None))

    def test_anonymous_is_not_an_admin(self):
        self.assertFalse(user_is_admin(AnonymousUser()))
        self.assertFalse(user_is_admin(_user(is_authenticated=False)))

    def test_inactive_staff_is_not_an_admin(self):
        self.assertFalse(user_is_admin(_user(is_active=False)))

    def test_non_staff_is_not_an_admin(self):
        self.assertFalse(user_is_admin(_user(is_staff=False)))

    def test_is_superuser_without_is_staff_is_not_an_admin(self):
        self.assertFalse(user_is_admin(_user(is_staff=False, is_superuser=True)))

    def test_missing_attributes_are_not_an_admin(self):
        self.assertFalse(user_is_admin(SimpleNamespace(is_authenticated=True, is_active=True)))


class UserCanAccessAppTest(SimpleTestCase):
    def test_an_admin_may_access_every_app(self):
        for label in APP_LABELS:
            with self.subTest(app=label):
                self.assertTrue(user_can_access_app(_user(), label))

    def test_anyone_else_may_access_no_app(self):
        users = {
            "none": None,
            "anonymous": AnonymousUser(),
            "inactive": _user(is_active=False),
            "non-staff": _user(is_staff=False),
            "superuser flag only": _user(is_staff=False, is_superuser=True),
        }
        for name, user in users.items():
            for label in APP_LABELS:
                with self.subTest(user=name, app=label):
                    self.assertFalse(user_can_access_app(user, label))


class AdminPredicateOnMembersTest(TestCase):
    """The same rule on real ``Member`` rows (the duck-typed attributes match the model)."""

    def test_member_rows(self):
        self.assertTrue(user_is_admin(make_admin(email="admin@example.com")))
        self.assertFalse(user_is_admin(make_member(email="member@example.com")))
        self.assertFalse(user_is_admin(make_admin(email="gone@example.com", is_active=False)))
