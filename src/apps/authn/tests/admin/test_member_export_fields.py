"""The Member admin export allowlist keeps sensitive columns out of the column picker."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase

Member = get_user_model()


class MemberExportFieldsTest(TestCase):
    def test_export_fields_exclude_sensitive_columns(self):
        """Without the explicit ``export_fields`` allowlist, the generic export offered (and
        previewed on the column-picker page) the base64 profile image, the password hash,
        ``is_superuser``, the ``admin_apps`` grant list and the vestigial AbstractUser ``email``."""
        member_admin = admin.site._registry[Member]

        exported = {name for name, _label in member_admin.get_export_fields()}

        for column in ("profile_image", "password", "is_superuser", "admin_apps", "email"):
            self.assertNotIn(column, exported)
        # Sanity check that the curated columns are the ones actually offered.
        self.assertIn("first_name", exported)
        self.assertIn("last_name", exported)
