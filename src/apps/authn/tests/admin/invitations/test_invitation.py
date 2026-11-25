"""Tests for AcceptInvitationView (Django view, not DRF)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.authn.models.members.admin_invitation import AdminInvitation

Member = get_user_model()


class _AcceptInvitationViewCase(TestCase):
    # noinspection PyMethodMayBeStatic
    def _inviter(self):
        inviter = getattr(self, "_sender", None)
        if inviter is None:
            inviter = self._sender = Member.objects.create_user(
                password="StrongPass123!", first_name="Sending", last_name="Admin", is_staff=True, is_active=True
            )
        return inviter

    def _create_invitation(self, email="invite@example.com", role=AdminInvitation.Role.ADMIN, **kwargs):
        defaults = {
            "invited_by": self._inviter(),
            "email": email,
            "token": AdminInvitation.generate_token(),
            "role": role,
            "status": AdminInvitation.Status.PENDING,
            "expires_at": timezone.now() + timezone.timedelta(days=7),
        }
        defaults.update(kwargs)
        return AdminInvitation.objects.create(**defaults)

    def _existing_verified_member(self, email="existing@example.com"):
        member = Member.objects.create_user(
            password="StrongPass123!", first_name="Ex", last_name="Member", is_staff=False, is_active=True
        )
        ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=True)
        return member


class AcceptInvitationViewTests(_AcceptInvitationViewCase):
    def test_get_valid_invitation_renders_form(self):
        invitation = self._create_invitation()
        response = self.client.get(f"/authn/invite/{invitation.token}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invite@example.com")

    def test_get_invalid_token_returns_error(self):
        response = self.client.get("/authn/invite/nonexistent-token/")
        self.assertEqual(response.status_code, 400)

    def test_get_expired_invitation_returns_error(self):
        invitation = self._create_invitation(
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        response = self.client.get(f"/authn/invite/{invitation.token}/")
        self.assertEqual(response.status_code, 400)

    def test_get_cancelled_invitation_returns_error(self):
        invitation = self._create_invitation(status=AdminInvitation.Status.CANCELLED)
        response = self.client.get(f"/authn/invite/{invitation.token}/")
        self.assertEqual(response.status_code, 400)

    def test_get_existing_verified_member_only_offers_the_upgrade(self):
        """A GET must not grant Admin: the link is emailed, so gateway scanners and browser
        prefetches follow it, and the request carries no CSRF protection."""
        invitation = self._create_invitation(email="existing@example.com")
        member = self._existing_verified_member()

        response = self.client.get(f"/authn/invite/{invitation.token}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "existing@example.com")
        self.assertContains(response, "Grant admin access")
        member.refresh_from_db()
        self.assertFalse(member.is_staff)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, AdminInvitation.Status.PENDING)

    def test_post_existing_verified_member_upgrades_and_shows_registered(self):
        invitation = self._create_invitation(email="existing@example.com")
        member = self._existing_verified_member()

        response = self.client.post(f"/authn/invite/{invitation.token}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "existing@example.com")
        member.refresh_from_db()
        # The existing account becomes a full Admin (the superuser column mirrors staff).
        self.assertTrue(member.is_staff)
        self.assertTrue(member.is_superuser)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, AdminInvitation.Status.ACCEPTED)

    def test_post_invalid_token_returns_error(self):
        response = self.client.post(
            "/authn/invite/nonexistent-token/",
            {"first_name": "A", "last_name": "B", "password1": "x", "password2": "x"},
        )
        self.assertEqual(response.status_code, 400)

    def test_post_rate_limited_returns_429(self):
        from django.core.cache import cache

        invitation = self._create_invitation(email="rl@example.com")
        cache.set(f"invitation-rate:{invitation.pk}", 10, timeout=3600)
        response = self.client.post(
            f"/authn/invite/{invitation.token}/",
            {"first_name": "A", "last_name": "B", "password1": "x", "password2": "x"},
        )
        self.assertEqual(response.status_code, 429)
        cache.clear()

    def test_post_attempts_on_a_real_invitation_are_counted_and_then_refused(self):
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        invitation = self._create_invitation(email="counted@example.com")
        body = {"email": "counted@example.com", "first_name": "A", "last_name": "B", "password1": "x", "password2": "y"}

        statuses = [self.client.post(f"/authn/invite/{invitation.token}/", body).status_code for _ in range(11)]

        self.assertEqual(statuses, [200] * 10 + [429])
        self.assertEqual(cache.get(f"invitation-rate:{invitation.pk}"), 10)

    def test_a_token_that_cannot_be_a_real_one_is_invalid_without_a_query(self):
        """PostgreSQL rejects a NUL in a string parameter; an over-long value can never match the column."""
        # With the request limiter on, the first request of a process loads its policy rows (then re-reads them only
        # every few seconds); load them before counting, so only the view's own queries are counted.
        self.client.get("/authn/invite/x/")
        for token in ("a%00b", "x" * 65, "x" * 200):
            for method in (self.client.get, self.client.post):
                with self.subTest(token=token[:8], method=method.__name__):
                    with self.assertNumQueries(0):
                        response = method(f"/authn/invite/{token}/")

                    self.assertEqual(response.status_code, 400)

    def test_post_with_made_up_tokens_writes_nothing_to_the_cache(self):
        """The token is caller-chosen: counting before the lookup would mint one cache entry per made-up token."""
        from unittest.mock import patch

        from apps.authn.views.admin.invitation import view as invitation_view

        with patch.object(invitation_view, "cache") as cache_mock:
            statuses = [
                self.client.post(f"/authn/invite/made-up-{index}/", {"first_name": "A"}).status_code
                for index in range(25)
            ]

        self.assertEqual(set(statuses), {400})
        cache_mock.get.assert_not_called()
        cache_mock.set.assert_not_called()

    def test_post_on_an_expired_or_used_invitation_is_not_counted(self):
        from unittest.mock import patch

        from apps.authn.views.admin.invitation import view as invitation_view

        expired = self._create_invitation(
            email="gone@example.com", expires_at=timezone.now() - timezone.timedelta(days=1)
        )
        with patch.object(invitation_view, "cache") as cache_mock:
            response = self.client.post(f"/authn/invite/{expired.token}/", {"first_name": "A"})

        self.assertEqual(response.status_code, 400)
        cache_mock.set.assert_not_called()

    def test_post_creates_an_admin(self):
        invitation = self._create_invitation()
        response = self.client.post(
            f"/authn/invite/{invitation.token}/",
            {
                "email": "invite@example.com",
                "first_name": "Staff",
                "last_name": "User",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        member = ContactEmail.objects.get(email_address="invite@example.com").member
        member.refresh_from_db()
        self.assertTrue(member.is_staff)
        self.assertTrue(member.is_active)
        self.assertTrue(member.is_superuser)
