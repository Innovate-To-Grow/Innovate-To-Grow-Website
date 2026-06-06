"""Targeted coverage for residual uncovered branches across authn.

Each test exercises a specific previously-uncovered line/branch and asserts on
the resulting behavior (return value, raised exception, DB state, or message).
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework import serializers

from apps.authn.models import ContactEmail

Member = get_user_model()


# ---------------------------------------------------------------------------
# admin/members/forms.py
# ---------------------------------------------------------------------------
class Base64ImageWidgetTests(SimpleTestCase):
    def _widget(self):
        from apps.authn.admin.members.forms import Base64ImageWidget

        return Base64ImageWidget()

    def test_value_from_datadict_clear_checkbox_returns_empty(self):
        """forms.py:37 — clear checkbox checked, no upload -> returns empty string."""
        widget = self._widget()
        name = "profile_image"
        clear_name = widget.clear_checkbox_name(name)
        result = widget.value_from_datadict({clear_name: "on"}, {}, name)
        self.assertEqual(result, "")

    def test_render_shows_preview_for_existing_base64(self):
        """forms.py:53-63 — long base64 value renders an <img> preview."""
        widget = self._widget()
        value = "data:image/png;base64," + ("A" * 60)
        html = widget.render("profile_image", value)
        self.assertIn("<img", html)
        self.assertIn(value, html)
        self.assertIn("Current image", html)

    def test_render_prepends_data_uri_for_bare_base64(self):
        """forms.py:53 — value without data: prefix gets a data:image/png prefix."""
        widget = self._widget()
        value = "B" * 60  # >50 chars, no "data:" prefix
        html = widget.render("profile_image", value)
        self.assertIn(f"data:image/png;base64,{value}", html)


class MemberCreationFormPasswordIncompleteTests(TestCase):
    def test_only_one_password_field_set_is_invalid(self):
        """forms.py:101-108 — one field filled, the other blank -> password_incomplete error."""
        from django.forms.utils import ErrorDict

        from apps.authn.admin.members.forms import MemberCreationForm

        form = MemberCreationForm(
            {
                "first_name": "Half",
                "last_name": "Password",
                "password1": "OnlyOnePass123!",
                "password2": "",
                "is_active": "on",
            }
        )
        # Pre-seed the form's internal state so add_error() inside validate_passwords()
        # records the error without re-triggering the full clean cascade.
        form.cleaned_data = {"password1": "OnlyOnePass123!", "password2": ""}
        form._errors = ErrorDict()
        form.validate_passwords()
        self.assertIn("password2", form._errors)
        self.assertEqual(form._errors["password2"].data[0].code, "password_incomplete")
        self.assertNotIn("set_usable_password", form.cleaned_data)


class MemberChangeFormClearImageTests(TestCase):
    def test_clear_checkbox_clears_image(self):
        """forms.py:129 — clear checkbox in submitted data clears the stored image."""
        from apps.authn.admin.members.forms import MemberChangeForm

        member = Member.objects.create_user(
            first_name="Avatar",
            last_name="User",
            password="StrongPass123!",
            profile_image="data:image/png;base64,old-image",
        )
        clear_name = MemberChangeForm().fields["profile_image"].widget.clear_checkbox_name("profile_image")
        data = {
            "password": member.password,
            "first_name": member.first_name,
            "middle_name": "",
            "last_name": member.last_name,
            "organization": "",
            "title": "",
            "profile_image": "",
            clear_name: "on",
            "is_active": "on",
            "is_staff": "",
            "is_superuser": "",
            "groups": [],
            "user_permissions": [],
            "last_login": "",
            "date_joined": member.date_joined.isoformat(),
        }
        form = MemberChangeForm(data=data, files={}, instance=member)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.profile_image, "")


class MemberImportFormValidationTests(SimpleTestCase):
    def test_wrong_extension_rejected(self):
        """forms.py:180 — non-xlsx/xls extension raises a validation error."""
        from apps.authn.admin.members.forms import MemberImportForm

        upload = SimpleUploadedFile("members.txt", b"data", content_type="text/plain")
        form = MemberImportForm(data={}, files={"excel_file": upload})
        self.assertFalse(form.is_valid())
        self.assertIn("excel_file", form.errors)
        self.assertIn(".xlsx or .xls", str(form.errors["excel_file"]))

    def test_oversized_file_rejected(self):
        """forms.py:184 — file larger than 5MB raises a validation error."""
        from apps.authn.admin.members.forms import MemberImportForm

        big = SimpleUploadedFile(
            "members.xlsx",
            b"x" * (5 * 1024 * 1024 + 1),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        form = MemberImportForm(data={}, files={"excel_file": big})
        self.assertFalse(form.is_valid())
        self.assertIn("excel_file", form.errors)
        self.assertIn("cannot exceed 5MB", str(form.errors["excel_file"]))


# ---------------------------------------------------------------------------
# admin/members/inlines.py
# ---------------------------------------------------------------------------
class NoneSafeFieldTests(SimpleTestCase):
    def test_uuid_field_treats_none_string_as_empty(self):
        """inlines.py:13-15 — NoneSafeUUIDField.to_python('None') -> None."""
        from apps.authn.admin.members.inlines import NoneSafeUUIDField

        field = NoneSafeUUIDField()
        self.assertIsNone(field.to_python("None"))
        self.assertIsNone(field.to_python(""))
        self.assertIsNone(field.to_python(None))

    def test_uuid_field_parses_real_uuid(self):
        """inlines.py:15 — a genuine UUID string falls through to super().to_python."""
        import uuid

        from apps.authn.admin.members.inlines import NoneSafeUUIDField

        value = uuid.uuid4()
        field = NoneSafeUUIDField()
        self.assertEqual(field.to_python(str(value)), value)


class NoneSafeInlineForeignKeyFieldTests(TestCase):
    def test_inline_fk_field_treats_none_string_as_empty(self):
        """inlines.py:31-32 — NoneSafeInlineForeignKeyField.clean('None') normalizes to None.

        Uses a REAL parent instance so the assertion discriminates: if the
        "None"->None normalization fires, clean() hits the empty-value path and
        returns the parent_instance; if it did NOT fire, the base class would
        compare str("None") against the parent pk and raise ValidationError.
        """
        from django.core.exceptions import ValidationError

        from apps.authn.admin.members.inlines import NoneSafeInlineForeignKeyField

        parent = Member.objects.create_user(password="x", first_name="P", last_name="Q")
        field = NoneSafeInlineForeignKeyField(parent_instance=parent, to_field="pk")

        # "None" is normalized to None -> empty path -> returns the parent instance.
        self.assertIs(field.clean("None"), parent)

        # Control: a non-matching, non-"None" value is NOT normalized and raises.
        with self.assertRaises(ValidationError):
            field.clean("not-the-parent-pk")


class UUIDInlineMixinTests(TestCase):
    def test_formfield_for_uuid_dbfield_gets_none_safe_class(self):
        """inlines.py:90 — formfield_for_dbfield reclasses a UUIDField to NoneSafeUUIDField."""
        from django.contrib.admin.sites import AdminSite

        from apps.authn.admin.members.inlines import ContactEmailInline, NoneSafeUUIDField
        from apps.authn.models import ContactEmail

        inline = ContactEmailInline(Member, AdminSite())
        request = RequestFactory().get("/")
        request.user = Member.objects.create_user(first_name="A", last_name="B", password="StrongPass123!")
        # The `id` field on ContactEmail is a UUID primary key.
        uuid_dbfield = ContactEmail._meta.get_field("id")
        formfield = inline.formfield_for_dbfield(uuid_dbfield, request)
        self.assertIsInstance(formfield, NoneSafeUUIDField)

    def test_normalize_replaces_none_string_in_querydict(self):
        """inlines.py:53 — setlist runs when a 'None' value is normalized to ''."""
        from django.http import QueryDict

        from apps.authn.admin.members.inlines import NoneSafeUUIDInlineFormSet

        data = QueryDict(mutable=True)
        data["contact_emails-0-id"] = "None"
        normalized = NoneSafeUUIDInlineFormSet._normalize_none_uuid_values(data, "contact_emails")
        self.assertEqual(normalized.get("contact_emails-0-id"), "")


@override_settings(ROOT_URLCONF="config.urls", ADMIN_REQUIRE_CONFIRMATION=False)
class ContactEmailInlinePrimaryFormsetTests(TestCase):
    """inlines.py:116 — submitting two primary emails through the admin is rejected."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.admin = Member.objects.create_superuser(
            password="admin123", first_name="Admin", last_name="User", is_staff=True, is_active=True
        )
        ContactEmail.objects.create(
            member=self.admin, email_address="admin@example.com", email_type="primary", verified=True
        )
        self.target = Member.objects.create_user(
            first_name="Target", last_name="User", password="target123", is_active=True
        )

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    def test_more_than_one_primary_raises_validation_error(self):
        self.client.force_login(self.admin)
        data = {
            "password1": "",
            "password2": "",
            "first_name": "Two",
            "middle_name": "",
            "last_name": "Primaries",
            "organization": "",
            "title": "",
            "is_active": "on",
            "contact_emails-TOTAL_FORMS": "2",
            "contact_emails-INITIAL_FORMS": "0",
            "contact_emails-MIN_NUM_FORMS": "0",
            "contact_emails-MAX_NUM_FORMS": "1000",
            "contact_emails-0-id": "None",
            "contact_emails-0-member": "None",
            "contact_emails-0-email_address": "first@example.com",
            "contact_emails-0-email_type": "primary",
            "contact_emails-0-verified": "on",
            "contact_emails-0-subscribe": "on",
            "contact_emails-1-id": "None",
            "contact_emails-1-member": "None",
            "contact_emails-1-email_address": "second@example.com",
            "contact_emails-1-email_type": "primary",
            "contact_emails-1-verified": "on",
            "contact_emails-1-subscribe": "on",
            "contact_phones-TOTAL_FORMS": "0",
            "contact_phones-INITIAL_FORMS": "0",
            "contact_phones-MIN_NUM_FORMS": "0",
            "contact_phones-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }
        resp = self.client.post("/admin/authn/member/add/", data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "A member may only have one primary email.")
        self.assertFalse(Member.objects.filter(first_name="Two", last_name="Primaries").exists())


# ---------------------------------------------------------------------------
# admin/members/member_helpers.py:103
# ---------------------------------------------------------------------------
class ImportResultMessageTests(TestCase):
    def test_import_view_appends_error_count_to_message(self):
        """member_helpers.py:103 — success message includes error count when errors present."""
        from apps.authn.admin.members import member_helpers
        from apps.authn.services.import_members.types import ImportResult

        captured = {}

        class FakeAdmin:
            def message_user(self, request, message, level=None):
                captured["message"] = message
                captured["level"] = level

        result = ImportResult(
            success=True,
            created_count=1,
            updated_count=0,
            skipped_count=0,
            errors=["row 5 bad email"],
        )

        request = RequestFactory().post("/import/", {})

        with (
            patch.object(member_helpers, "MemberImportForm") as FormCls,
            patch(
                "apps.authn.services.import_members.import_members_from_excel",
                return_value=result,
            ),
            patch.object(member_helpers, "build_import_context", return_value={}),
            patch.object(member_helpers, "render", return_value="rendered"),
        ):
            form = FormCls.return_value
            form.is_valid.return_value = True
            form.cleaned_data = {"excel_file": object(), "set_password": "", "update_existing": False}
            member_helpers.import_excel_view(FakeAdmin(), request)

        self.assertIn("1 error(s)", captured["message"])
        self.assertEqual(captured["level"], "warning")


# ---------------------------------------------------------------------------
# apps.py:13-14
# ---------------------------------------------------------------------------
class AppConfigReadyTests(SimpleTestCase):
    def test_ready_swallows_import_error(self):
        """apps.py:11-14 — ready() catches ImportError from the signals import.

        Make `from . import signals` raise ImportError and assert (a) ready()
        does NOT propagate it, and (b) the failing import was actually attempted
        (so the except branch ran, not some earlier return).
        """
        import builtins

        from apps.authn.apps import AuthnConfig

        config = AuthnConfig.create("apps.authn")
        real_import = builtins.__import__
        attempted = {"signals": False}

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if level == 1 and fromlist and "signals" in fromlist:
                attempted["signals"] = True
                raise ImportError("boom")
            return real_import(name, globals, locals, fromlist, level)

        with patch.object(builtins, "__import__", side_effect=fake_import):
            config.ready()  # must not raise

        self.assertTrue(attempted["signals"], "ready() should have attempted the signals import")


# ---------------------------------------------------------------------------
# models/members/admin_invitation.py
# ---------------------------------------------------------------------------
class AdminInvitationModelTests(TestCase):
    def _invitation(self):
        from apps.authn.models.members.admin_invitation import AdminInvitation

        return AdminInvitation.objects.create(
            email="invite@example.com",
            token=AdminInvitation.generate_token(),
            expires_at=AdminInvitation.default_expiry(),
        )

    def test_mark_cancelled_sets_status(self):
        """admin_invitation.py:75-76 — mark_cancelled() persists CANCELLED status."""
        from apps.authn.models.members.admin_invitation import AdminInvitation

        inv = self._invitation()
        inv.mark_cancelled()
        inv.refresh_from_db()
        self.assertEqual(inv.status, AdminInvitation.Status.CANCELLED)

    def test_get_acceptance_url_without_request_returns_path(self):
        """admin_invitation.py:84 — get_acceptance_url() with no request returns a relative path."""
        inv = self._invitation()
        url = inv.get_acceptance_url()
        self.assertIn(inv.token, url)
        self.assertTrue(url.startswith("/"))


# ---------------------------------------------------------------------------
# serializers/contact_emails/__init__.py:34,50
# ---------------------------------------------------------------------------
class ContactEmailSerializerValidateMethodTests(SimpleTestCase):
    def test_create_validate_email_type_rejects_primary(self):
        """contact_emails:34 — validate_email_type('primary') raises in create serializer."""
        from apps.authn.serializers.contact_emails import ContactEmailCreateSerializer

        with self.assertRaises(serializers.ValidationError):
            ContactEmailCreateSerializer().validate_email_type("primary")

    def test_update_validate_email_type_rejects_primary(self):
        """contact_emails:50 — validate_email_type('primary') raises in update serializer."""
        from apps.authn.serializers.contact_emails import ContactEmailUpdateSerializer

        with self.assertRaises(serializers.ValidationError):
            ContactEmailUpdateSerializer().validate_email_type("primary")


# ---------------------------------------------------------------------------
# serializers/contact_phones/__init__.py:43,66,85
# ---------------------------------------------------------------------------
class ContactPhoneSerializerValidationTests(SimpleTestCase):
    def test_blank_phone_number_rejected(self):
        """contact_phones:43 — phone normalizing to empty raises 'required'."""
        from apps.authn.serializers.contact_phones import ContactPhoneCreateSerializer

        with self.assertRaises(serializers.ValidationError) as ctx:
            ContactPhoneCreateSerializer().validate_phone_number("()- .")
        self.assertIn("required", str(ctx.exception))

    def test_invalid_region_rejected(self):
        """contact_phones:66 — region not in valid set raises 'Invalid region'."""
        from apps.authn.serializers.contact_phones import ContactPhoneCreateSerializer

        with self.assertRaises(serializers.ValidationError) as ctx:
            ContactPhoneCreateSerializer().validate_region("not-a-real-region")
        self.assertIn("Invalid region", str(ctx.exception))

    def test_verify_code_rejects_non_six_digit(self):
        """contact_phones:85 — non 6-digit code rejected."""
        from apps.authn.serializers.contact_phones import ContactPhoneVerifyCodeSerializer

        with self.assertRaises(serializers.ValidationError):
            ContactPhoneVerifyCodeSerializer().validate_code("12ab56")


# ---------------------------------------------------------------------------
# serializers/profile.py:70-71
# ---------------------------------------------------------------------------
class ProfileSerializerImageErrorTests(TestCase):
    def test_profile_image_attribute_error_yields_none(self):
        """profile.py:70-71 — profile_image without .startswith -> None (AttributeError path)."""
        from apps.authn.serializers.profile import ProfileSerializer

        member = Member.objects.create_user(first_name="Img", last_name="Err", password="StrongPass123!")
        ContactEmail.objects.create(member=member, email_address="img@example.com", email_type="primary", verified=True)
        # Bypass model field validation: set a non-string truthy value directly.
        member.profile_image = 12345  # int -> .startswith raises AttributeError

        data = ProfileSerializer().to_representation(member)
        self.assertIsNone(data["profile_image"])


# ---------------------------------------------------------------------------
# serializers/register.py:136-137, 146-153  (pending-member race paths)
# ---------------------------------------------------------------------------
class RegisterSerializerRaceTests(TestCase):
    def _data(self, email="race@example.com"):
        return {
            "email": email,
            "password": "encpw",
            "password_confirm": "encpw",
            "first_name": "Race",
            "last_name": "Winner",
            "organization": "Org",
        }

    def test_claim_none_pending_exists_uses_pending(self):
        """register.py:136-137 — claim returns None but a pending member exists -> reuse it."""
        from apps.authn.serializers.register import RegisterSerializer

        pending = Member.objects.create_user(first_name="", last_name="", is_active=False)

        serializer = RegisterSerializer(data=self._data())
        serializer.initial_data  # noqa: B018 - ensure data attached
        # Bypass email validation race-conflict by pre-validating.
        with (
            patch("apps.authn.serializers.register.decrypt_password_pair", return_value="plain123"),
            patch("apps.authn.serializers.register.get_pending_registration_member", return_value=None),
            patch("apps.authn.serializers.register.registration_email_conflicts", return_value=False),
        ):
            self.assertTrue(serializer.is_valid(), serializer.errors)

        with (
            patch("apps.authn.serializers.register.claim_unclaimed_contact_email", return_value=None),
            patch(
                "apps.authn.serializers.register.get_pending_registration_member",
                return_value=pending,
            ),
            patch("apps.authn.serializers.register.issue_email_challenge"),
        ):
            member = serializer.save()

        self.assertEqual(member.pk, pending.pk)
        self.assertEqual(member.first_name, "Race")

    def test_claim_none_integrity_error_pending_appears(self):
        """register.py:146-153 — ContactEmail.create IntegrityError, pending then found -> reuse."""
        from apps.authn.serializers.register import RegisterSerializer

        pending = Member.objects.create_user(first_name="", last_name="", is_active=False)

        serializer = RegisterSerializer(data=self._data("race2@example.com"))
        with (
            patch("apps.authn.serializers.register.decrypt_password_pair", return_value="plain123"),
            patch("apps.authn.serializers.register.get_pending_registration_member", return_value=None),
            patch("apps.authn.serializers.register.registration_email_conflicts", return_value=False),
        ):
            self.assertTrue(serializer.is_valid(), serializer.errors)

        # get_pending: first call (None) goes into create branch; second call returns pending.
        with (
            patch("apps.authn.serializers.register.claim_unclaimed_contact_email", return_value=None),
            patch(
                "apps.authn.serializers.register.get_pending_registration_member",
                side_effect=[None, pending],
            ),
            patch("apps.authn.models.ContactEmail.objects.create", side_effect=IntegrityError("dup")),
            patch("apps.authn.serializers.register.issue_email_challenge"),
        ):
            member = serializer.save()

        self.assertEqual(member.pk, pending.pk)

    def test_claim_none_integrity_error_no_pending_raises(self):
        """register.py:146-153 — IntegrityError and still no pending -> ValidationError."""
        from apps.authn.serializers.register import RegisterSerializer

        serializer = RegisterSerializer(data=self._data("race3@example.com"))
        with (
            patch("apps.authn.serializers.register.decrypt_password_pair", return_value="plain123"),
            patch("apps.authn.serializers.register.get_pending_registration_member", return_value=None),
            patch("apps.authn.serializers.register.registration_email_conflicts", return_value=False),
        ):
            self.assertTrue(serializer.is_valid(), serializer.errors)

        with (
            patch("apps.authn.serializers.register.claim_unclaimed_contact_email", return_value=None),
            patch(
                "apps.authn.serializers.register.get_pending_registration_member",
                side_effect=[None, None],
            ),
            patch("apps.authn.models.ContactEmail.objects.create", side_effect=IntegrityError("dup")),
            patch("apps.authn.serializers.register.issue_email_challenge"),
        ):
            with self.assertRaises(serializers.ValidationError):
                serializer.save()


# ---------------------------------------------------------------------------
# serializers/email_code/auth.py:81  (IntegrityError -> pending then found)
# ---------------------------------------------------------------------------
class UnifiedEmailAuthCreatePendingRaceTests(TestCase):
    def test_create_pending_integrity_then_pending_found(self):
        """auth.py:76-81 — ContactEmail.create IntegrityError, pending found -> reuse it."""
        from apps.authn.serializers.email_code.auth import UnifiedEmailAuthRequestSerializer

        pending = Member.objects.create_user(first_name="", last_name="", is_active=False)
        serializer = UnifiedEmailAuthRequestSerializer()

        with (
            patch(
                "apps.authn.serializers.email_code.auth.claim_unclaimed_contact_email",
                return_value=None,
            ),
            patch(
                "apps.authn.serializers.email_code.auth.get_pending_registration_member",
                side_effect=[None, pending],
            ),
            patch("apps.authn.models.ContactEmail.objects.create", side_effect=IntegrityError("dup")),
        ):
            result = serializer._create_pending_member("authrace@example.com")

        self.assertEqual(result.pk, pending.pk)

    def test_create_pending_integrity_no_pending_raises(self):
        """auth.py:82 — IntegrityError and no pending -> ValidationError."""
        from apps.authn.serializers.email_code.auth import UnifiedEmailAuthRequestSerializer

        serializer = UnifiedEmailAuthRequestSerializer()
        with (
            patch(
                "apps.authn.serializers.email_code.auth.claim_unclaimed_contact_email",
                return_value=None,
            ),
            patch(
                "apps.authn.serializers.email_code.auth.get_pending_registration_member",
                side_effect=[None, None],
            ),
            patch("apps.authn.models.ContactEmail.objects.create", side_effect=IntegrityError("dup")),
        ):
            with self.assertRaises(serializers.ValidationError):
                serializer._create_pending_member("authrace2@example.com")


# ---------------------------------------------------------------------------
# services/rsa_manager.py:62
# ---------------------------------------------------------------------------
class RotateAuthKeypairTests(TestCase):
    def test_rotate_with_no_keypair_creates_and_rotates(self):
        """rsa_manager.py:62 — rotate_auth_keypair(None) resolves a keypair then rotates."""
        from apps.authn.models import RSAKeypair
        from apps.authn.services import rsa_manager

        self.assertEqual(RSAKeypair.objects.count(), 0)
        keypair = rsa_manager.rotate_auth_keypair(None)
        self.assertIsNotNone(keypair.pk)
        self.assertTrue(keypair.is_active)


# ---------------------------------------------------------------------------
# views/account/change_password.py:53-54  (TokenError on blacklist)
# ---------------------------------------------------------------------------
class ChangePasswordTokenErrorTests(TestCase):
    def test_invalid_refresh_token_logs_warning_and_succeeds(self):
        """change_password.py:53-54 — bad refresh token logs warning, password still changes."""
        from rest_framework.test import APIClient

        member = Member.objects.create_user(first_name="CP", last_name="User", password="OldPass123!", is_active=True)
        ContactEmail.objects.create(member=member, email_address="cp@example.com", email_type="primary", verified=True)
        client = APIClient()
        client.force_authenticate(member)

        with (
            patch(
                "apps.authn.serializers.change_password.ChangePasswordSerializer.is_valid",
                return_value=True,
            ),
            patch(
                "apps.authn.serializers.change_password.ChangePasswordSerializer.validated_data",
                new={"_decrypted_new_password": "BrandNewPass123!"},
                create=True,
            ),
            self.assertLogs("apps.authn.views.account.change_password", level="WARNING") as logs,
        ):
            response = client.post(
                "/authn/change-password/",
                {"refresh": "not-a-valid-jwt-token"},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("access", response.data)
        self.assertTrue(any("Failed to blacklist" in m for m in logs.output))
        member.refresh_from_db()
        self.assertTrue(member.check_password("BrandNewPass123!"))


# ---------------------------------------------------------------------------
# views/admin/invitation.py:36  (_get_unfold_context no each_context)
# ---------------------------------------------------------------------------
class UnfoldContextTests(SimpleTestCase):
    def test_get_unfold_context_returns_empty_without_each_context(self):
        """invitation.py:36 — site without each_context returns {}."""
        from apps.authn.views.admin import invitation

        request = RequestFactory().get("/")

        class _Site:
            pass

        with patch.object(invitation.admin, "site", _Site()):
            ctx = invitation._get_unfold_context(request)
        self.assertEqual(ctx, {})


# ---------------------------------------------------------------------------
# views/auth/email_code_helpers.py:15, 32
# ---------------------------------------------------------------------------
class EmailCodeHelperResponseTests(SimpleTestCase):
    def test_request_code_invalid_serializer_returns_400(self):
        """email_code_helpers.py:15 — invalid serializer -> 400 with errors."""
        from types import SimpleNamespace

        from apps.authn.views.auth import email_code_helpers

        request = SimpleNamespace(data={})

        class _Serializer:
            def __init__(self, data=None):
                self.errors = {"email": ["required"]}

            def is_valid(self):
                return False

        response = email_code_helpers.request_code_response(request, _Serializer)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"email": ["required"]})

    def test_auth_challenge_invalid_returns_400(self):
        """email_code_helpers.py:32 — AuthChallengeInvalid on save -> 400 generic detail."""
        from types import SimpleNamespace

        from apps.authn.constants import VERIFICATION_INVALID
        from apps.authn.services import AuthChallengeInvalid
        from apps.authn.views.auth import email_code_helpers

        request = SimpleNamespace(data={})

        class _Serializer:
            def __init__(self, data=None):
                pass

            def is_valid(self):
                return True

            def save(self):
                raise AuthChallengeInvalid("bad")

        response = email_code_helpers.auth_challenge_response(request, _Serializer)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": VERIFICATION_INVALID})


# ---------------------------------------------------------------------------
# views/unsubscribe_login.py:32  (_send_unsubscribe_confirmation no primary email)
# ---------------------------------------------------------------------------
class UnsubscribeConfirmationTests(TestCase):
    def test_no_primary_email_skips_send(self):
        """unsubscribe_login.py:32 — member without primary email -> send_notification_email not called."""
        from apps.authn.views import unsubscribe_login

        member = Member.objects.create_user(first_name="No", last_name="Email", is_active=True)

        with patch("apps.authn.services.email.send_notification_email") as send_mock:
            unsubscribe_login._send_unsubscribe_confirmation(member)

        send_mock.assert_not_called()


# ---------------------------------------------------------------------------
# views/admin/login/view.py password-mode fallback and email_code.py:112-113
# ---------------------------------------------------------------------------
@override_settings(ROOT_URLCONF="config.urls")
class AdminPasswordModeDisabledTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    def test_password_mode_post_uses_email_step_instead(self):
        """Password-only admin posts are treated as email-code login attempts."""
        response = self.client.post(
            "/admin/login/",
            {"mode": "password", "email": "someone@example.com"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["step"], "email")
        self.assertFalse(response.wsgi_request.user.is_authenticated)


@override_settings(ROOT_URLCONF="config.urls")
class AdminEmailCodeStateMissingTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    def test_code_step_without_email_state_falls_back_to_email(self):
        """email_code.py:112-113 — code step with empty email/member_id clears session, shows email form."""
        # Seed the session so dispatch routes to _handle_code_step, but leave
        # email/member_id unset so the guard at lines 111-113 fires.
        session = self.client.session
        session["admin_login_step"] = "code"
        session["admin_login_email"] = ""
        session.save()

        response = self.client.post(
            "/admin/login/",
            {"code": "123456"},
        )
        self.assertEqual(response.status_code, 200)
        # Fell back to the email entry step; session state cleared.
        self.assertEqual(response.context["step"], "email")
        self.assertNotIn("admin_login_step", self.client.session)
