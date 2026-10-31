"""Installed certificates (``MicrosoftGraphCertificate``) and what they mean for ``MicrosoftGraphProviderConfig``."""

import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from apps.core.admin.mixins.confirm_on_save_utils import SENSITIVE_FIELD_RE as CONFIRM_SENSITIVE_FIELD_RE
from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.services.db_tools.safe_orm import SENSITIVE_FIELD_RE as SAFE_ORM_SENSITIVE_FIELD_RE
from apps.core.tests.graph_helpers import create_graph_config, install_test_certificate

State = MicrosoftGraphCertificate.State
OTHER_CLIENT_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
SENDER = "i2g@contoso.com"


class CertificateRowTests(TestCase):
    def setUp(self):
        self.config = create_graph_config(name="Graph", is_active=True, certificate=False, scope=(SENDER,))

    def test_a_config_holds_at_most_one_current_and_one_previous_certificate(self):
        install_test_certificate(self.config)
        install_test_certificate(self.config, state=State.PREVIOUS)
        for state in (State.CURRENT, State.PREVIOUS):
            with self.subTest(state), self.assertRaises(IntegrityError), transaction.atomic():
                install_test_certificate(self.config, state=state)

        install_test_certificate(self.config, state=State.REMOVED)
        install_test_certificate(self.config, state=State.REMOVED)
        self.assertEqual(self.config.certificates.count(), 4)

    def test_each_config_has_its_own_current_certificate(self):
        standby = create_graph_config(name="Standby", scope=(SENDER,))
        current = install_test_certificate(self.config)

        self.assertEqual(self.config.current_certificate, current)
        self.assertNotEqual(standby.current_certificate, current)

    def test_validity_and_usability(self):
        certificate = install_test_certificate(self.config)
        self.assertTrue(certificate.valid_now())
        self.assertFalse(certificate.expired)
        self.assertTrue(certificate.usable_for(self.config))

        cases = {
            "expired": {"not_after": timezone.now() - datetime.timedelta(seconds=1)},
            "not valid yet": {"not_before": timezone.now() + datetime.timedelta(minutes=1)},
            "previous": {"state": State.PREVIOUS},
            "no stored key": {"store_version_id": ""},
            "no key reference": {"store_arn": ""},
            "another app": {"client_id": OTHER_CLIENT_ID},
            "another tenant": {"tenant_id": "contoso.onmicrosoft.com"},
        }
        for label, changes in cases.items():
            with self.subTest(label):
                changed = MicrosoftGraphCertificate(**{**_values(certificate), **changes})
                self.assertFalse(changed.usable_for(self.config))

    def test_str_names_the_thumbprint_state_and_expiry_only(self):
        certificate = install_test_certificate(self.config)

        self.assertEqual(
            str(certificate), f"{certificate.sha1_thumbprint} (Current, valid until {certificate.not_after:%Y-%m-%d})"
        )

    def test_deleting_a_config_deletes_its_certificate_rows(self):
        config = create_graph_config(name="Old", scope=(SENDER,))

        config.delete()

        self.assertFalse(MicrosoftGraphCertificate.objects.filter(config_id=config.pk).exists())

    def test_no_column_of_the_graph_tables_looks_like_a_secret(self):
        # Field names stay readable in audit text, confirm diffs and exports only if neither regex flags them.
        for model in (MicrosoftGraphProviderConfig, MicrosoftGraphCertificate):
            with connection.cursor() as cursor:
                columns = [
                    column.name
                    for column in connection.introspection.get_table_description(cursor, model._meta.db_table)
                ]
            for column in columns:
                with self.subTest(model=model.__name__, column=column):
                    self.assertIsNone(CONFIRM_SENSITIVE_FIELD_RE.search(column))
                    self.assertIsNone(SAFE_ORM_SENSITIVE_FIELD_RE.search(column))
                    self.assertNotIn("key_pem", column)


class ConfigCertificateTests(TestCase):
    def setUp(self):
        self.config = create_graph_config(name="Graph", is_active=True, scope=(SENDER,))
        self.current = self.config.current_certificate

    def test_a_current_certificate_makes_a_scoped_config_ready(self):
        self.assertTrue(self.config.credential_configured)
        self.assertTrue(self.config.is_configured)
        self.assertTrue(self.config.sending_ready(SENDER))
        self.assertEqual(self.config.certificate_expires_at, self.current.not_after)
        self.assertFalse(self.config.certificate_expired)

    def test_an_expired_or_not_yet_valid_certificate_is_not_ready(self):
        for label, changes in {
            "expired": {"not_after": timezone.now() - datetime.timedelta(minutes=1)},
            "not valid yet": {"not_before": timezone.now() + datetime.timedelta(days=1)},
        }.items():
            with self.subTest(label):
                MicrosoftGraphCertificate.objects.filter(pk=self.current.pk).update(**changes)

                self.assertFalse(self.config.credential_configured)
                self.assertFalse(self.config.is_configured)
                MicrosoftGraphCertificate.objects.filter(pk=self.current.pk).update(
                    not_before=self.current.not_before, not_after=self.current.not_after
                )
        MicrosoftGraphCertificate.objects.filter(pk=self.current.pk).update(not_after=timezone.now())
        self.assertTrue(self.config.certificate_expired)

    def test_previous_and_removed_certificates_never_make_a_config_ready(self):
        self.current.state = State.PREVIOUS
        self.current.save()

        self.assertEqual(self.config.previous_certificate, self.current)
        self.assertIsNone(self.config.current_certificate)
        self.assertFalse(self.config.is_configured)

    def test_the_application_cannot_change_under_an_installed_certificate(self):
        for field, value in (("client_id", OTHER_CLIENT_ID), ("tenant_id", "contoso.onmicrosoft.com")):
            with self.subTest(field):
                config = MicrosoftGraphProviderConfig.objects.get(pk=self.config.pk)
                setattr(config, field, value)

                with self.assertRaises(ValidationError) as caught:
                    config.save()

                self.assertEqual(list(caught.exception.message_dict), [field])
                self.assertIn("Remove the installed certificates", caught.exception.message_dict[field][0])

    def test_a_previous_certificate_also_pins_the_application(self):
        self.current.state = State.PREVIOUS
        self.current.save()
        self.config.client_id = OTHER_CLIENT_ID

        with self.assertRaises(ValidationError):
            self.config.save()

    def test_the_application_may_change_once_the_certificates_are_removed(self):
        self.config.certificates.update(state=State.REMOVED)
        self.config.client_id = OTHER_CLIENT_ID

        self.config.save()

        self.config.refresh_from_db()
        self.assertEqual(self.config.client_id, OTHER_CLIENT_ID)

    def test_other_edits_are_unaffected_by_the_certificate(self):
        self.config.name = "Renamed"
        self.config.mailbox = SENDER

        self.config.save()

        self.config.refresh_from_db()
        self.assertEqual(self.config.name, "Renamed")

    def test_an_unsaved_config_has_no_certificates(self):
        config = MicrosoftGraphProviderConfig()

        self.assertIsNone(config.current_certificate)
        self.assertIsNone(config.previous_certificate)
        self.assertFalse(config.credential_configured)
        self.assertFalse(config.certificate_expired)


def _values(certificate):
    return {
        field.attname: getattr(certificate, field.attname)
        for field in MicrosoftGraphCertificate._meta.concrete_fields
        if not field.primary_key
    }
