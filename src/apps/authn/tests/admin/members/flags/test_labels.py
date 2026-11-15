"""Labels and help text: "Account active" is the account, Verified is sign-in, Subscribed is newsletters."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.admin.members import help_texts
from apps.authn.admin.members.contact.email import ContactEmailAdminForm
from apps.authn.admin.members.contact.phone_verification import ContactPhoneAdminForm
from apps.authn.admin.members.forms import MemberChangeForm, MemberCreationForm
from apps.authn.admin.members.inlines import ContactEmailInlineForm
from apps.authn.models import ContactEmail, ContactPhone

Member = get_user_model()


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class AccountActiveLabelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.master = Member.objects.create_superuser(password="StrongPass123!", first_name="Ada", last_name="Master")
        cls.helper = Member.objects.create_user(
            first_name="Hal", last_name="Helper", is_active=True, is_staff=True, admin_apps=["authn"]
        )
        cls.staffer = Member.objects.create_user(first_name="Sam", last_name="Staff", is_active=True, is_staff=True)
        cls.jane = Member.objects.create_user(first_name="Jane", last_name="Doe", is_active=True)
        ContactEmail.objects.create(member=cls.jane, email_address="jane@example.com", verified=True)
        ContactPhone.objects.create(member=cls.jane, phone_number="2095550110")

    def setUp(self):
        cache.clear()
        self.client.force_login(self.master)

    def tearDown(self):
        cache.clear()

    def test_the_forms_say_account_active_without_a_migration(self):
        for form_class in (MemberChangeForm, MemberCreationForm):
            with self.subTest(form=form_class.__name__):
                self.assertEqual(form_class._meta.labels["is_active"], "Account active")
                self.assertIn("not the tool for a bounced address", form_class._meta.help_texts["is_active"])
        # The model keeps Django's own wording: nothing here needs authn/0024.
        self.assertEqual(Member._meta.get_field("is_active").verbose_name, "active")

    def test_the_member_page_has_an_account_section(self):
        response = self.client.get(reverse("admin:authn_member_change", args=[self.jane.pk]))

        model_admin = response.context["adminform"].model_admin
        fieldsets = {
            str(name): options for name, options in model_admin.get_fieldsets(response.wsgi_request, self.jane)
        }
        self.assertEqual(fieldsets["Account"]["fields"], ("is_active", "registration_pending"))
        self.assertNotIn("is_active", fieldsets["Permissions"]["fields"])
        self.assertContains(response, "Account active")
        self.assertContains(response, "Unfinished sign-up")
        self.assertContains(response, "Mark undeliverable")

    def test_the_read_only_flag_on_a_staff_account_is_labelled_too(self):
        self.client.force_login(self.helper)

        response = self.client.get(reverse("admin:authn_member_change", args=[self.staffer.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("is_active", response.context["adminform"].readonly_fields)
        self.assertContains(response, "Account active")
        self.assertContains(response, "not the tool for a bounced address")

    def test_the_add_page_says_account_active(self):
        self.assertContains(self.client.get(reverse("admin:authn_member_add")), "Account active")

    def test_the_member_page_explains_the_address_flags(self):
        response = self.client.get(reverse("admin:authn_member_change", args=[self.jane.pk]))

        self.assertContains(response, "Verified (sign-in)")
        self.assertContains(response, "Subscribed (newsletters)")
        self.assertContains(response, "It does not stop any mail.")
        self.assertContains(response, "Replying STOP turns it off.")

    def test_the_contact_forms_share_the_wording(self):
        for form_class in (ContactEmailAdminForm, ContactEmailInlineForm):
            with self.subTest(form=form_class.__name__):
                form = form_class()
                self.assertEqual(form.fields["verified"].label, "Verified (sign-in)")
                self.assertEqual(form.fields["verified"].help_text, help_texts.EMAIL_VERIFIED)
                self.assertEqual(form.fields["subscribe"].help_text, help_texts.EMAIL_SUBSCRIBED)
                self.assertIn("Switch primary email", form.fields["email_type"].help_text)
        self.assertEqual(ContactPhoneAdminForm().fields["subscribe"].help_text, help_texts.PHONE_SUBSCRIBED)

    def test_the_contact_email_page_explains_the_flags(self):
        contact = ContactEmail.objects.get(email_address="jane@example.com")

        response = self.client.get(reverse("admin:authn_contactemail_change", args=[contact.pk]))

        self.assertContains(response, "It does not stop any mail.")
        self.assertContains(response, "All active members, Staff, Selected members and event audiences ignore it.")
