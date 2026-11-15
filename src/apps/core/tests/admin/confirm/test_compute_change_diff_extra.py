from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.admin.confirmation.diff import compute_change_diff
from apps.core.admin.confirmation.values import format_field_value


class ComputeChangeDiffExtraTest(TestCase):
    def test_skips_changed_field_not_in_form_fields(self):
        from apps.cms.models import CMSEmbedAllowedHost

        obj = CMSEmbedAllowedHost.objects.create(hostname="x.com", is_active=True)
        form = MagicMock()
        form.changed_data = ["hostname", "phantom"]
        form.fields = {"hostname": MagicMock(label="Hostname")}
        form.cleaned_data = {"hostname": "y.com", "phantom": "z"}

        diff = compute_change_diff(CMSEmbedAllowedHost, obj.pk, form)
        fields = [d["field"] for d in diff]
        self.assertIn("hostname", fields)
        self.assertNotIn("phantom", fields)

    def test_get_field_exception_falls_back_to_getattr(self):
        from apps.cms.models import CMSEmbedAllowedHost

        obj = CMSEmbedAllowedHost.objects.create(hostname="x.com", is_active=True)
        form = MagicMock()
        form.changed_data = ["is_active"]
        form.fields = {"is_active": MagicMock(label="Active")}
        form.cleaned_data = {"is_active": False}

        real_get_field = CMSEmbedAllowedHost._meta.get_field

        def selective(name, *args, **kwargs):
            # Only blow up for the diff lookup of "is_active"; let the ORM's
            # internal get_field calls (used by objects.get) work normally.
            if name == "is_active":
                raise Exception("no field")
            return real_get_field(name, *args, **kwargs)

        with patch.object(CMSEmbedAllowedHost._meta, "get_field", side_effect=selective):
            diff = compute_change_diff(CMSEmbedAllowedHost, obj.pk, form)
        self.assertEqual(diff[0]["old_value"], "Yes")  # original is_active=True

    def test_foreign_key_old_value(self):
        """A changed FK field resolves the related object via getattr."""
        from apps.event.models import CheckIn, Event

        event = Event.objects.create(
            name="E",
            slug="e-fk",
            date="2025-06-15",
            end_date="2025-06-15",
            location="L",
        )
        check_in = CheckIn.objects.create(event=event, name="Door")
        form = MagicMock()
        form.changed_data = ["event"]
        form.fields = {"event": MagicMock(label="Event")}
        new_event = Event.objects.create(
            name="E2",
            slug="e2-fk",
            date="2025-06-16",
            end_date="2025-06-16",
            location="L2",
        )
        form.cleaned_data = {"event": new_event}

        diff = compute_change_diff(CheckIn, check_in.pk, form)
        self.assertEqual(diff[0]["old_value"], str(event))


class FormatFieldValueExtraTest(TestCase):
    def test_real_model_instance(self):
        from apps.projects.models import Semester

        semester = Semester.objects.create(year=2025, season=1, is_published=True)
        self.assertEqual(format_field_value(semester), str(semester))

    def test_queryset_joined(self):
        from apps.projects.models import Semester

        Semester.objects.create(year=2025, season=1, is_published=True)
        Semester.objects.create(year=2024, season=1, is_published=True)
        result = format_field_value(Semester.objects.all())
        self.assertIn(",", result)

    def test_unserializable_list_falls_back_to_str(self):
        class Weird:
            def __repr__(self):
                return "WEIRD"

        # json.dumps with default=str usually succeeds; force a TypeError instead.
        with patch("json.dumps", side_effect=TypeError("nope")):
            result = format_field_value([Weird()])
        self.assertIn("WEIRD", result)
