"""The Message Trace toggle: its permission is tenant-wide and beyond the InfoSec approval, so where go-live evidence
is required it stays off until the InfoSec exception reference is recorded (or the role is approved)."""

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.core.models import MicrosoftGraphProviderConfig
from apps.core.models.base.service_credentials.microsoft_graph import MESSAGE_TRACE_NEEDS_REVIEW, MESSAGE_TRACE_ROLE
from apps.core.tests.project.models.graph.config.test_microsoft_graph_config import graph_fields


def enabled(**overrides) -> MicrosoftGraphProviderConfig:
    return MicrosoftGraphProviderConfig(**graph_fields(message_trace_enabled=True, **overrides))


class MessageTraceToggleTests(TestCase):
    def test_it_is_off_by_default(self):
        self.assertFalse(MicrosoftGraphProviderConfig(**graph_fields()).message_trace_enabled)

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_in_production_it_needs_the_infosec_reference(self):
        with self.assertRaises(ValidationError) as error:
            enabled().full_clean(validate_constraints=False)

        self.assertEqual(error.exception.message_dict["message_trace_enabled"], [MESSAGE_TRACE_NEEDS_REVIEW])

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_a_blank_reference_does_not_count(self):
        with self.assertRaises(ValidationError):
            enabled(permission_exception_reference="   ").full_clean(validate_constraints=False)

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_in_production_the_reference_allows_it(self):
        enabled(permission_exception_reference="INFOSEC-123").full_clean(validate_constraints=False)

    @override_settings(
        GRAPH_REQUIRE_ACCESS_EVIDENCE=True,
        GRAPH_APPROVED_APPLICATION_ROLES=("Mail.Send", "Mail.ReadWrite", MESSAGE_TRACE_ROLE),
    )
    def test_an_approved_role_allows_it_without_a_reference(self):
        enabled().full_clean(validate_constraints=False)

    def test_without_the_go_live_gate_it_can_be_turned_on(self):
        enabled().full_clean(validate_constraints=False)

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_turning_it_off_is_always_allowed(self):
        MicrosoftGraphProviderConfig(**graph_fields(message_trace_enabled=False)).full_clean(validate_constraints=False)
