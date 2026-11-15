import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

import apps.core.admin.confirmation.diff as logger_module
from apps.core.admin.confirmation.diff import compute_change_diff, compute_delete_diff


class ComputeChangeDiffTest(TestCase):
    def test_returns_changed_fields_only(self):
        from apps.cms.models import CMSEmbedAllowedHost

        obj = CMSEmbedAllowedHost.objects.create(hostname="old.com", is_active=True)

        form = MagicMock()
        form.changed_data = ["hostname"]
        form.fields = {"hostname": MagicMock(label="Hostname")}
        form.cleaned_data = {"hostname": "new.com"}

        diff = compute_change_diff(CMSEmbedAllowedHost, obj.pk, form)

        self.assertEqual(len(diff), 1)
        self.assertEqual(diff[0]["old_value"], "old.com")
        self.assertEqual(diff[0]["new_value"], "new.com")

    def test_empty_changed_data_returns_empty(self):
        from apps.cms.models import CMSEmbedAllowedHost

        form = MagicMock()
        form.changed_data = []

        diff = compute_change_diff(CMSEmbedAllowedHost, "fake-id", form)

        self.assertEqual(diff, [])

    def test_nonexistent_object_returns_empty(self):
        from apps.cms.models import CMSEmbedAllowedHost

        form = MagicMock()
        form.changed_data = ["hostname"]
        form.fields = {"hostname": MagicMock(label="Hostname")}
        form.cleaned_data = {"hostname": "new.com"}

        diff = compute_change_diff(CMSEmbedAllowedHost, uuid.uuid4(), form)

        self.assertEqual(diff, [])


class ComputeDeleteDiffTest(TestCase):
    def test_returns_field_values_for_object(self):
        from apps.cms.models import CMSEmbedAllowedHost

        obj = CMSEmbedAllowedHost.objects.create(hostname="delete-me.com", is_active=True)

        diff = compute_delete_diff(obj)

        field_names = [d["field"] for d in diff]
        self.assertIn("hostname", field_names)
        self.assertIn("is_active", field_names)

        hostname_entry = next(d for d in diff if d["field"] == "hostname")
        self.assertEqual(hostname_entry["value"], "delete-me.com")

    def test_excludes_id_field(self):
        from apps.cms.models import CMSEmbedAllowedHost

        obj = CMSEmbedAllowedHost.objects.create(hostname="no-id.com", is_active=True)

        diff = compute_delete_diff(obj)

        field_names = [d["field"] for d in diff]
        self.assertNotIn("id", field_names)

    def test_skips_reverse_relations_without_column(self):
        """Reverse relations (no `column` attr) are skipped in the delete diff."""
        from apps.event.models import Event

        event = Event.objects.create(
            name="E",
            slug="del-rev",
            date="2025-06-15",
            end_date="2025-06-15",
            location="L",
        )
        diff = compute_delete_diff(event)
        field_names = [d["field"] for d in diff]
        # Concrete columns appear...
        self.assertIn("name", field_names)
        # ...but the reverse "registrations" relation (no column) is skipped.
        self.assertNotIn("registrations", field_names)

    def test_skips_fields_that_raise(self):
        """A field whose value access raises is skipped (logged at debug)."""

        class _BoomField:
            name = "explodes"
            column = "explodes"
            verbose_name = "Explodes"

        class _OkField:
            name = "ok_field"
            column = "ok_field"
            verbose_name = "Ok Field"

        class _Meta:
            @staticmethod
            def get_fields():
                return [_BoomField(), _OkField()]

        class _FakeObj:
            _meta = _Meta()

            def __getattribute__(self, item):
                if item == "explodes":
                    raise RuntimeError("cannot read")
                return super().__getattribute__(item)

            ok_field = "fine"

        with patch.object(logger_module.logger, "debug") as debug_log:
            diff = compute_delete_diff(_FakeObj())

        field_names = [d["field"] for d in diff]
        self.assertNotIn("explodes", field_names)
        self.assertIn("ok_field", field_names)
        debug_log.assert_called_once()
