from django.core.exceptions import PermissionDenied

from apps.authn.admin.members.contact.email import ContactEmailAdmin
from apps.authn.admin.members.contact.email_form import ContactEmailAdminForm
from apps.authn.models import (
    ContactEmail,
)
from apps.authn.tests.admin.actions.test_admin_actions import Member, _AdminTestBase, _request


class ContactEmailAdminTests(_AdminTestBase):
    def setUp(self):
        super().setUp()
        self.model_admin = ContactEmailAdmin(ContactEmail, self.site)
        self.member = Member.objects.create_user(password="t", first_name="C", last_name="E")
        self.email = ContactEmail.objects.create(
            member=self.member, email_address="c@example.com", email_type="primary", subscribe=False
        )

    def test_mark_verified(self):
        request = _request(self.rf, self.admin_user)
        self.model_admin.mark_verified(request, ContactEmail.objects.filter(pk=self.email.pk))
        self.email.refresh_from_db()
        self.assertTrue(self.email.verified)
        self.assertIn("1 email(s) marked as verified.", self._messages(request))

    def test_mark_unverified(self):
        self.email.verified = True
        self.email.save(update_fields=["verified"])
        request = _request(self.rf, self.admin_user)
        self.model_admin.mark_unverified(request, ContactEmail.objects.filter(pk=self.email.pk))
        self.email.refresh_from_db()
        self.assertFalse(self.email.verified)
        self.assertIn("1 email(s) marked as unverified.", self._messages(request))

    def test_toggle_subscribe(self):
        request = _request(self.rf, self.admin_user)
        self.model_admin.toggle_subscribe(request, ContactEmail.objects.filter(pk=self.email.pk))
        self.email.refresh_from_db()
        self.assertTrue(self.email.subscribe)
        self.assertTrue(any("Toggled subscription" in m for m in self._messages(request)))

    def test_primary_identity_fields_are_readonly(self):
        readonly = self.model_admin.get_readonly_fields(
            _request(self.rf, self.admin_user),
            self.email,
        )
        self.assertTrue({"member", "email_address", "email_type"}.issubset(readonly))

    def test_primary_form_rejects_forged_identity_edit(self):
        form = ContactEmailAdminForm(
            data={
                "member": str(self.member.pk),
                "email_address": "rewritten@example.com",
                "email_type": "primary",
                "verified": "",
                "subscribe": "",
            },
            instance=self.email,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("cannot be edited directly", str(form.non_field_errors()))

    def test_save_model_rejects_primary_demotion(self):
        self.email.email_type = "secondary"

        with self.assertRaisesMessage(PermissionDenied, "cannot be edited directly"):
            self.model_admin.save_model(
                _request(self.rf, self.admin_user),
                self.email,
                form=None,
                change=True,
            )

        self.email.refresh_from_db()
        self.assertEqual(self.email.email_type, "primary")

    def test_save_model_rejects_direct_primary_promotion(self):
        secondary = ContactEmail.objects.create(
            member=self.member,
            email_address="secondary@example.com",
            email_type="secondary",
            verified=True,
        )
        secondary.email_type = "primary"

        with self.assertRaisesMessage(PermissionDenied, "cannot be assigned directly"):
            self.model_admin.save_model(
                _request(self.rf, self.admin_user),
                secondary,
                form=None,
                change=True,
            )

        secondary.refresh_from_db()
        self.assertEqual(secondary.email_type, "secondary")

    def test_primary_cannot_be_deleted_directly_or_in_bulk(self):
        request = _request(self.rf, self.admin_user)
        self.assertFalse(self.model_admin.has_delete_permission(request, self.email))

        with self.assertRaisesMessage(PermissionDenied, "cannot be deleted directly"):
            self.model_admin.delete_model(request, self.email)
        with self.assertRaisesMessage(PermissionDenied, "cannot be deleted directly"):
            self.model_admin.delete_queryset(
                request,
                ContactEmail.objects.filter(pk=self.email.pk),
            )

        self.assertTrue(ContactEmail.objects.filter(pk=self.email.pk).exists())

    def test_make_primary_action_uses_atomic_swap_service(self):
        secondary = ContactEmail.objects.create(
            member=self.member,
            email_address="secondary@example.com",
            email_type="secondary",
            verified=True,
        )
        request = _request(self.rf, self.admin_user)

        self.model_admin.make_primary(
            request,
            ContactEmail.objects.filter(pk=secondary.pk),
        )

        self.email.refresh_from_db()
        secondary.refresh_from_db()
        self.assertEqual(self.email.email_type, "secondary")
        self.assertEqual(secondary.email_type, "primary")
        self.assertIn(
            "secondary@example.com is now the primary email of C E. c@example.com is now the secondary. "
            "No subscription or verification changed, and nothing was sent.",
            self._messages(request),
        )

    def test_make_primary_action_requires_exactly_one_email(self):
        secondary = ContactEmail.objects.create(
            member=self.member,
            email_address="secondary@example.com",
            email_type="secondary",
            verified=True,
        )
        request = _request(self.rf, self.admin_user)

        self.model_admin.make_primary(
            request,
            ContactEmail.objects.filter(pk__in=(self.email.pk, secondary.pk)),
        )

        self.email.refresh_from_db()
        secondary.refresh_from_db()
        self.assertEqual(self.email.email_type, "primary")
        self.assertEqual(secondary.email_type, "secondary")
        self.assertIn("Select exactly one email to make primary.", self._messages(request))
