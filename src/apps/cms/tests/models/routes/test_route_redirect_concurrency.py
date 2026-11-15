"""PostgreSQL interleaving tests for redirect activation and page writes."""

import threading
from unittest import skipUnless
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase, override_settings

from apps.cms.models import CMSPage, RouteRedirect
from apps.cms.services.routing import route_write_locks


@skipUnless(connection.vendor == "postgresql", "requires PostgreSQL row/advisory lock semantics")
@override_settings(AMPLIFY_APP_ID="", BACKGROUND_JOBS_ENABLED=False)
class RouteRedirectPageConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.page = CMSPage.objects.create(
            slug="concurrent-redirect-target",
            route="/concurrent-redirect-target",
            title="Concurrent Redirect Target",
            status="published",
        )
        self.redirect = RouteRedirect.objects.create(
            source_path="/legacy-concurrent-target",
            destination_path=self.page.route,
            is_active=False,
        )

    def _interleave(self, *, first_write, second_prepare, second_write):
        """Hold the first commit while the second writer reaches the route lock."""

        first_written = threading.Event()
        release_first = threading.Event()
        second_prepared = threading.Event()
        second_lock_attempted = threading.Event()
        errors = {}
        real_acquire = route_write_locks._acquire_route_advisory_locks

        def observe_route_lock(routes):
            if threading.current_thread().name == "cms-route-second":
                second_lock_attempted.set()
            return real_acquire(routes)

        def run_first():
            close_old_connections()
            try:
                with transaction.atomic():
                    first_write()
                    first_written.set()
                    if not release_first.wait(timeout=10):
                        raise TimeoutError("test did not release the first CMS route writer")
            except Exception as exc:  # noqa: BLE001 - surfaced in the main test thread.
                errors["first"] = exc
                first_written.set()
                release_first.set()
            finally:
                connections.close_all()

        def run_second():
            close_old_connections()
            try:
                with transaction.atomic():
                    prepared = second_prepare()
                    second_prepared.set()
                    second_write(prepared)
            except Exception as exc:  # noqa: BLE001 - the losing ValidationError is asserted below.
                errors["second"] = exc
                second_prepared.set()
            finally:
                connections.close_all()

        with patch.object(
            route_write_locks,
            "_acquire_route_advisory_locks",
            side_effect=observe_route_lock,
        ):
            first_thread = threading.Thread(target=run_first, name="cms-route-first")
            first_thread.start()
            self.assertTrue(first_written.wait(timeout=10))
            if "first" in errors:
                release_first.set()
                first_thread.join(timeout=10)
                raise errors["first"]

            second_thread = threading.Thread(target=run_second, name="cms-route-second")
            second_thread.start()
            self.assertTrue(second_prepared.wait(timeout=10))
            self.assertTrue(second_lock_attempted.wait(timeout=10))
            self.assertTrue(second_thread.is_alive())

            release_first.set()
            first_thread.join(timeout=10)
            second_thread.join(timeout=10)

        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertNotIn("first", errors)
        return errors.get("second")

    def _activate_redirect(self):
        redirect = RouteRedirect.objects.get(pk=self.redirect.pk)
        redirect.is_active = True
        redirect.save(update_fields=["is_active", "updated_at"])

    @staticmethod
    def _set_page_status(page, status):
        page.status = status
        page.save(update_fields=["status", "updated_at"])

    def test_activation_committing_first_rejects_concurrent_unpublish(self):
        error = self._interleave(
            first_write=self._activate_redirect,
            second_prepare=lambda: CMSPage.objects.get(pk=self.page.pk),
            second_write=lambda page: self._set_page_status(page, "draft"),
        )

        self.assertIsInstance(error, ValidationError)
        self.page.refresh_from_db()
        self.redirect.refresh_from_db()
        self.assertEqual(self.page.status, "published")
        self.assertTrue(self.redirect.is_active)

    def test_archive_committing_first_rejects_concurrent_activation(self):
        error = self._interleave(
            first_write=lambda: self._set_page_status(
                CMSPage.objects.get(pk=self.page.pk),
                "archived",
            ),
            second_prepare=lambda: RouteRedirect.objects.get(pk=self.redirect.pk),
            second_write=lambda redirect: (
                setattr(redirect, "is_active", True),
                redirect.save(update_fields=["is_active", "updated_at"]),
            ),
        )

        self.assertIsInstance(error, ValidationError)
        self.page.refresh_from_db()
        self.redirect.refresh_from_db()
        self.assertEqual(self.page.status, "archived")
        self.assertFalse(self.redirect.is_active)

    def test_delete_committing_first_rejects_concurrent_activation(self):
        error = self._interleave(
            first_write=lambda: CMSPage.objects.get(pk=self.page.pk).delete(),
            second_prepare=lambda: RouteRedirect.objects.get(pk=self.redirect.pk),
            second_write=lambda redirect: (
                setattr(redirect, "is_active", True),
                redirect.save(update_fields=["is_active", "updated_at"]),
            ),
        )

        self.assertIsInstance(error, ValidationError)
        self.assertFalse(CMSPage.objects.filter(pk=self.page.pk).exists())
        self.redirect.refresh_from_db()
        self.assertFalse(self.redirect.is_active)

    def test_activation_committing_first_rejects_concurrent_delete(self):
        error = self._interleave(
            first_write=self._activate_redirect,
            second_prepare=lambda: CMSPage.objects.get(pk=self.page.pk),
            second_write=lambda page: page.delete(),
        )

        self.assertIsInstance(error, ValidationError)
        self.assertTrue(CMSPage.objects.filter(pk=self.page.pk).exists())
        self.redirect.refresh_from_db()
        self.assertTrue(self.redirect.is_active)
