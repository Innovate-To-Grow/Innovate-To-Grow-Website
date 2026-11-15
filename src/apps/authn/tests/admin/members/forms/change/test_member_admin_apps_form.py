"""Tests for the ``admin_apps`` field on the Member admin change form.

The foundation replaced the per-model ``user_permissions`` widget with a
multi-select of registered admin app labels backed by ``Member.admin_apps``
(see apps.authn.admin.members.member.forms.MemberChangeForm and apps.core.utils.access).
These tests assert the change form renders the new control, exposes the
registered app labels as choices, persists a submitted selection, and no
longer exposes ``user_permissions``.

The admin restricts the form's editable fields to those in ``MemberAdmin``'s
fieldsets (``admin_apps`` is in; ``user_permissions`` is out), so assertions go
through the admin-bound form (``MemberAdmin.get_form``) and the real change
page rather than the raw ``__all__`` form class.
"""

from django import forms
from django.contrib import admin
from django.test import RequestFactory, TestCase

from apps.authn.admin.members.member.forms import admin_app_choices
from apps.authn.models import Member


def _admin_change_form(obj):
    """Return the admin-bound change form class for ``obj`` (restricted by fieldsets)."""
    model_admin = admin.site._registry[Member]
    request = RequestFactory().get("/")
    request.user = Member(is_superuser=True, is_staff=True, is_active=True)
    return model_admin.get_form(request, obj=obj, change=True)


class MemberChangeFormFieldTests(TestCase):
    """Assertions on the admin-bound change form (the surface operators see)."""

    def setUp(self):
        self.member = Member.objects.create_user(
            password="StrongPass123!", first_name="Form", last_name="Field", is_staff=True
        )

    def test_admin_apps_is_a_multi_select(self):
        form = _admin_change_form(self.member)()
        field = form.fields["admin_apps"]
        self.assertIsInstance(field, forms.MultipleChoiceField)
        self.assertIsInstance(field.widget, forms.CheckboxSelectMultiple)
        self.assertFalse(field.required)

    def test_user_permissions_is_not_a_form_field(self):
        form = _admin_change_form(self.member)()
        self.assertNotIn("user_permissions", form.fields)

    def test_admin_apps_choices_include_registered_admin_apps(self):
        form = _admin_change_form(self.member)()
        labels = {value for value, _label in form.fields["admin_apps"].choices}
        for expected in ("cms", "event", "authn"):
            self.assertIn(expected, labels)

    def test_admin_app_choices_helper_matches_registry(self):
        labels = {value for value, _label in admin_app_choices()}
        registry_labels = {model._meta.app_label for model in admin.site._registry}
        self.assertEqual(labels, registry_labels)

    def test_admin_app_choice_labels_include_label_in_parens(self):
        choices = dict(admin_app_choices())
        # Rendered as "<verbose name> (<label>)" for operator clarity.
        self.assertIn("(authn)", choices["authn"])

    def test_admin_bound_form_persists_admin_apps(self):
        FormClass = _admin_change_form(self.member)
        form = FormClass(
            data={
                "first_name": "Form",
                "last_name": "Field",
                "is_active": "on",
                "is_staff": "on",
                "admin_apps": ["cms", "event"],
            },
            instance=self.member,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        saved.refresh_from_db()
        self.assertEqual(sorted(saved.admin_apps), ["cms", "event"])

    def test_admin_bound_form_rejects_unregistered_app_label(self):
        FormClass = _admin_change_form(self.member)
        form = FormClass(
            data={
                "first_name": "Form",
                "last_name": "Field",
                "is_active": "on",
                "is_staff": "on",
                "admin_apps": ["not_a_real_app"],
            },
            instance=self.member,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("admin_apps", form.errors)
