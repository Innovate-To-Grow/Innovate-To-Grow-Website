from django.contrib import admin
from django.test import RequestFactory, TestCase

from apps.authn.models import Member


class AdminSwitchFieldTests(TestCase):
    """The change form offers one account-type switch, **Admin** (``is_staff``), to every Admin on every other member.

    ``is_superuser`` mirrors it on save and is bound by no form, nor are ``groups`` / ``user_permissions``.
    """

    def setUp(self):
        self.model_admin = admin.site._registry[Member]
        # A concrete instance so UserAdmin returns the *change* form (obj=None yields the add form).
        self.target = Member.objects.create_user(
            password="StrongPass123!", first_name="Edit", last_name="Target", is_staff=True, is_active=True
        )
        # An Admin made with ``is_staff`` only: no superuser path is involved.
        self.request = RequestFactory().get("/")
        self.request.user = Member(is_staff=True, is_active=True)

    def test_admin_is_editable_by_any_admin(self):
        self.assertNotIn("is_staff", self.model_admin.get_readonly_fields(self.request, self.target))
        form_class = self.model_admin.get_form(self.request, obj=self.target, change=True)
        self.assertIn("is_staff", form_class.base_fields)
        self.assertEqual(form_class.base_fields["is_staff"].label, "Admin")
        self.assertEqual(
            form_class.base_fields["is_staff"].help_text,
            "Can sign in to the admin site and manage everything in it. All Admins have the same permissions.",
        )

    def test_no_other_permission_field_is_bound(self):
        for obj in (self.target, None):
            form_class = self.model_admin.get_form(self.request, obj=obj, change=obj is not None)
            for field in ("is_superuser", "admin_apps", "groups", "user_permissions"):
                with self.subTest(change=obj is not None, field=field):
                    self.assertNotIn(field, form_class.base_fields)

    def test_the_add_form_creates_a_regular_member(self):
        form_class = self.model_admin.get_form(self.request, obj=None, change=False)
        self.assertNotIn("is_staff", form_class.base_fields)

    def test_the_fieldset_is_admin_access(self):
        fieldsets = dict(self.model_admin.get_fieldsets(self.request, self.target))
        self.assertEqual(fieldsets["Admin access"]["fields"], ("is_staff",))
