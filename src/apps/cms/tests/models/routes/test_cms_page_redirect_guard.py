from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cms.models import CMSPage, RouteRedirect


class CMSPageRedirectGuardTests(TestCase):
    def test_full_clean_rejects_application_reserved_and_redirect_sources(self):
        target = CMSPage.objects.create(
            slug="ownership-target",
            route="/ownership-target",
            title="Ownership Target",
            status="published",
        )
        RouteRedirect.objects.create(source_path="/legacy-owned", destination_path=target.route)

        for index, route in enumerate(("/schedule", "/admin/settings", "/legacy-owned")):
            with self.subTest(route=route), self.assertRaises(ValidationError):
                CMSPage(
                    slug=f"collision-{index}",
                    route=route,
                    title="Collision",
                    status="draft",
                ).full_clean()

    def test_active_redirect_prevents_destination_from_being_archived(self):
        page = CMSPage.objects.create(
            slug="archive-target",
            route="/archive-target",
            title="Archive Target",
            status="published",
        )
        RouteRedirect.objects.create(
            source_path="/old-archive-target",
            destination_path=page.route,
            is_active=True,
        )

        page.status = "archived"
        with self.assertRaises(ValidationError) as caught:
            page.save()
        self.assertIn("Disable or retarget", str(caught.exception))

    def test_active_redirect_prevents_destination_hard_delete(self):
        page = CMSPage.objects.create(
            slug="delete-target",
            route="/delete-target",
            title="Delete Target",
            status="published",
        )
        RouteRedirect.objects.create(
            source_path="/old-delete-target",
            destination_path=page.route,
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            page.delete()
        with self.assertRaises(ValidationError):
            CMSPage.objects.filter(pk=page.pk).delete()

    def test_inactive_redirect_does_not_block_archive(self):
        page = CMSPage.objects.create(
            slug="inactive-target",
            route="/inactive-target",
            title="Inactive Target",
            status="published",
        )
        RouteRedirect.objects.create(
            source_path="/old-inactive-target",
            destination_path=page.route,
            is_active=False,
        )

        page.status = "archived"
        page.save()
        self.assertEqual(page.status, "archived")
