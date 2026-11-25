"""Members for the "every Admin is equal" tests: two Admins made with ``is_staff`` only, and a regular member."""

from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, Member

PASSWORD = "StrongPass123!"


def make_admin_member(**kwargs):
    """An Admin made the plain way (``is_staff``, not ``create_superuser``), so no superuser path can be involved."""
    return Member.objects.create_user(password=PASSWORD, is_staff=True, is_active=True, **kwargs)


class AdminPeersCase(TestCase):
    """``self.admin`` is signed in; ``self.other_admin`` is another Admin; ``self.regular`` is a regular member."""

    def setUp(self):
        cache.clear()
        self.admin = make_admin_member(first_name="Ada", last_name="Admin")
        ContactEmail.objects.create(
            member=self.admin, email_address="ada.admin@example.com", email_type="primary", verified=True
        )
        self.other_admin = make_admin_member(first_name="Otto", last_name="Admin")
        ContactEmail.objects.create(
            member=self.other_admin, email_address="otto.admin@example.com", email_type="primary", verified=True
        )
        self.regular = Member.objects.create_user(password=PASSWORD, first_name="Reg", last_name="Ular", is_active=True)
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    @staticmethod
    def password_url(target):
        return f"/admin/authn/member/{target.pk}/password/"

    def changelist_action(self, action, members, **extra):
        return self.client.post(
            "/admin/authn/member/",
            {"action": action, "_selected_action": [str(member.pk) for member in members], "index": "0", **extra},
        )
