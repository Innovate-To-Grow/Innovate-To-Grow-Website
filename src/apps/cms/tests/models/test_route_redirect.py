"""Model and conflict-domain tests for CMS route redirects."""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cms.models import CMSPage, RouteRedirect
from apps.cms.services.route_redirects import redirect_mapping_conflicts


class RouteRedirectModelTests(TestCase):
    def setUp(self):
        self.target = CMSPage.objects.create(
            slug="redirect-target",
            route="/redirect-target",
            title="Redirect Target",
            status="published",
        )

    def test_defaults_and_path_normalization_preserve_case(self):
        redirect = RouteRedirect.objects.create(
            source_path="Legacy///FAQs/",
            destination_path="/redirect-target/",
        )

        self.assertEqual(redirect.source_path, "/Legacy/FAQs")
        self.assertEqual(redirect.destination_path, "/redirect-target")
        self.assertFalse(redirect.is_active)
        self.assertEqual(redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)
        self.assertFalse(redirect.edge_rule_managed)

    def test_legacy_source_supports_safe_punctuation_and_percent_decoding(self):
        redirect = RouteRedirect.objects.create(
            source_path="/Archive%2Ev1/~old+page/",
            destination_path="/redirect-target",
        )
        self.assertEqual(redirect.source_path, "/Archive.v1/~old+page")

    def test_rejects_external_query_fragment_backslash_and_control_paths(self):
        invalid_sources = (
            "https://example.com/old",
            "/old?campaign=email",
            "/old#section",
            "/old\\path",
            "/old\npath",
            "//example.com/old",
            "/old/%2e%2e/admin",
            "/old/%2Fadmin",
            "/old/%ZZ",
        )
        for index, source in enumerate(invalid_sources):
            with self.subTest(source=source), self.assertRaises(ValidationError):
                RouteRedirect.objects.create(
                    source_path=source,
                    destination_path="/redirect-target",
                    notes=str(index),
                )

    def test_rejects_cms_application_dynamic_reserved_and_root_sources(self):
        sources = (
            "/redirect-target",
            "/schedule",
            "/NEWS",
            "/events/fall-2026",
            "/EVENTS/fall-2026",
            "/admin/cms",
            "/robots.txt",
            "/SITEMAP.XML",
            "/_block-preview",
            "/_BLOCK-PREVIEW",
            "/",
        )
        for source in sources:
            with self.subTest(source=source), self.assertRaises(ValidationError):
                RouteRedirect.objects.create(source_path=source, destination_path="/redirect-target")

    def test_root_is_valid_destination(self):
        redirect = RouteRedirect.objects.create(source_path="/legacy-home", destination_path="/")
        self.assertEqual(redirect.destination_path, "/")

    def test_destination_must_be_published_page_or_application_route(self):
        CMSPage.objects.create(slug="draft-target", route="/draft-target", title="Draft", status="draft")

        with self.assertRaises(ValidationError):
            RouteRedirect.objects.create(source_path="/old-draft", destination_path="/draft-target")
        with self.assertRaises(ValidationError):
            RouteRedirect.objects.create(source_path="/old-missing", destination_path="/missing")
        with self.assertRaises(ValidationError):
            RouteRedirect.objects.create(source_path="/old-dynamic", destination_path="/news/missing-id")

        redirect = RouteRedirect.objects.create(source_path="/old-schedule", destination_path="/schedule")
        self.assertEqual(redirect.destination_path, "/schedule")

    def test_destination_keeps_strict_cms_syntax(self):
        for destination in ("/Archive.v1", "//schedule"):
            with self.subTest(destination=destination), self.assertRaises(ValidationError):
                RouteRedirect.objects.create(source_path="/old-punctuation", destination_path=destination)

    def test_rejects_self_redirect(self):
        with self.assertRaises(ValidationError) as caught:
            RouteRedirect.objects.create(source_path="/same", destination_path="/same")
        self.assertIn("same path", str(caught.exception))

    def test_rejects_redirect_chain(self):
        # bulk_create intentionally constructs legacy/stale state so the domain
        # detector can prove it closes chains even if old data bypassed clean().
        RouteRedirect.objects.bulk_create([RouteRedirect(source_path="/middle", destination_path="/redirect-target")])

        _source, _destination, conflicts = redirect_mapping_conflicts("/legacy", "/middle")
        self.assertIn("redirect_chain", {conflict.code for conflict in conflicts})

    def test_source_is_immutable(self):
        redirect = RouteRedirect.objects.create(source_path="/legacy", destination_path="/redirect-target")
        redirect.source_path = "/different"
        with self.assertRaises(ValidationError):
            redirect.save()

    def test_delete_is_blocked(self):
        redirect = RouteRedirect.objects.create(source_path="/legacy", destination_path="/redirect-target")
        with self.assertRaises(ValidationError):
            redirect.delete()

    def test_queryset_delete_is_blocked(self):
        redirect = RouteRedirect.objects.create(source_path="/legacy-queryset", destination_path="/redirect-target")
        with self.assertRaises(ValidationError):
            RouteRedirect.objects.filter(pk=redirect.pk).delete()

    def test_deactivation_remains_available_when_source_becomes_conflicted(self):
        redirect = RouteRedirect.objects.create(
            source_path="/legacy-recovery",
            destination_path="/redirect-target",
            is_active=True,
        )
        with patch(
            "apps.cms.services.route_redirects.PUBLIC_APP_ROUTES",
            [{"url": "/legacy-recovery", "title": "New App Route"}],
        ):
            redirect.is_active = False
            redirect.full_clean()
            redirect.save(update_fields=["is_active", "updated_at"])
            redirect.is_active = True
            with self.assertRaises(ValidationError):
                redirect.full_clean()

        redirect.refresh_from_db()
        self.assertFalse(redirect.is_active)

    def test_inactive_maintenance_allows_stale_source_but_reactivation_does_not(self):
        other_target = CMSPage.objects.create(
            slug="redirect-other-target",
            route="/redirect-other-target",
            title="Other Redirect Target",
            status="published",
        )
        redirect = RouteRedirect.objects.create(
            source_path="/legacy-maintenance",
            destination_path="/redirect-target",
            is_active=False,
        )

        with patch(
            "apps.cms.services.route_redirects.PUBLIC_APP_ROUTES",
            [{"url": "/legacy-maintenance", "title": "New App Route"}],
        ):
            redirect.destination_path = other_target.route
            redirect.save(update_fields=["destination_path", "updated_at"])
            redirect.is_active = True
            with self.assertRaises(ValidationError):
                redirect.save(update_fields=["is_active", "updated_at"])

        redirect.refresh_from_db()
        self.assertEqual(redirect.destination_path, other_target.route)
        self.assertFalse(redirect.is_active)


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
