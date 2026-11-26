"""The Admin lockout rules: nobody removes their own Admin account, and the last active Admin always stays."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase

from apps.authn.services.members.admins import DEACTIVATE, DELETE, DEMOTE, admin_removal_refusal

Member = get_user_model()

ACTIONS = (DELETE, DEACTIVATE, DEMOTE)


def _member(**kw):
    return Member.objects.create_user(password="StrongPass123!", first_name="A", last_name="B", **kw)


class AdminRemovalRefusalTests(TestCase):
    def setUp(self):
        self.alice = _member(is_staff=True)
        self.bob = _member(is_staff=True)

    def test_nobody_removes_their_own_admin_account(self):
        for action in ACTIONS:
            with self.subTest(action=action):
                refusal = admin_removal_refusal(self.alice, [self.alice], action=action)
                self.assertIn("your own Admin account", refusal)

    def test_the_self_rule_names_the_action(self):
        self.assertIn("cannot delete your own", admin_removal_refusal(self.alice, [self.alice], action=DELETE))
        self.assertIn("cannot deactivate your own", admin_removal_refusal(self.alice, [self.alice], action=DEACTIVATE))
        self.assertIn(
            "cannot remove Admin access from your own", admin_removal_refusal(self.alice, [self.alice], action=DEMOTE)
        )

    def test_an_admin_may_remove_another_admin(self):
        for action in ACTIONS:
            with self.subTest(action=action):
                self.assertEqual(admin_removal_refusal(self.alice, [self.bob], action=action), "")

    def test_the_last_active_admin_is_never_removed(self):
        self.bob.delete()
        for action in ACTIONS:
            with self.subTest(action=action):
                refusal = admin_removal_refusal(None, [self.alice], action=action)
                self.assertIn("this Admin account: the site must keep at least one active Admin", refusal)

    def test_an_inactive_admin_does_not_count_as_remaining(self):
        self.bob.is_active = False
        self.bob.save()
        refusal = admin_removal_refusal(None, [self.alice], action=DEACTIVATE)
        self.assertIn("at least one active Admin", refusal)

    def test_removing_every_admin_at_once_is_refused(self):
        regular = _member()
        refusal = admin_removal_refusal(regular, Member.objects.filter(is_staff=True), action=DELETE)
        self.assertIn("these Admin accounts: the site must keep at least one active Admin", refusal)

    def test_a_selection_that_includes_the_actor_is_refused(self):
        carol = _member(is_staff=True)
        refusal = admin_removal_refusal(self.alice, [self.bob, self.alice, carol], action=DEMOTE)
        self.assertIn("your own Admin account", refusal)

    def test_a_selection_of_other_admins_that_leaves_one_is_allowed(self):
        carol = _member(is_staff=True)
        self.assertEqual(admin_removal_refusal(self.alice, [self.bob, carol], action=DELETE), "")

    def test_regular_and_inactive_targets_are_never_refused(self):
        self.bob.delete()
        regular = _member()
        inactive_admin = _member(is_staff=True, is_active=False)
        for action in ACTIONS:
            with self.subTest(action=action):
                self.assertEqual(admin_removal_refusal(self.alice, [regular, inactive_admin], action=action), "")
                self.assertEqual(admin_removal_refusal(None, [], action=action), "")

    def test_a_regular_member_removing_themselves_is_allowed(self):
        regular = _member()
        self.assertEqual(admin_removal_refusal(regular, [regular], action=DELETE), "")

    def test_a_system_actor_only_gets_the_last_admin_rule(self):
        self.assertEqual(admin_removal_refusal(None, [self.alice], action=DELETE), "")

    def test_an_unknown_action_is_a_programming_error(self):
        with self.assertRaisesMessage(ValueError, "Unknown admin removal action: 'promote'"):
            admin_removal_refusal(self.alice, [self.bob], action="promote")

    def test_inside_a_transaction_the_remaining_admins_are_locked(self):
        from django.db.models.query import QuerySet

        original = QuerySet.select_for_update
        with patch.object(QuerySet, "select_for_update", autospec=True, side_effect=original) as lock:
            with transaction.atomic():
                self.assertEqual(admin_removal_refusal(self.alice, [self.bob], action=DELETE), "")
        lock.assert_called_once()

    def test_outside_a_transaction_nothing_is_locked(self):
        from django.db.models.query import QuerySet

        with patch.object(QuerySet, "select_for_update") as lock:
            with patch("apps.authn.services.members.admins.lockout.transaction.get_connection") as connection:
                connection.return_value.in_atomic_block = False
                self.assertEqual(admin_removal_refusal(self.alice, [self.bob], action=DELETE), "")
        lock.assert_not_called()
