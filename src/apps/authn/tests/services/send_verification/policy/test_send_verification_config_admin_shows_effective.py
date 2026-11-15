from django.contrib.admin import AdminSite
from django.test import override_settings

from apps.authn.admin.security.send_verification import SendVerificationConfigAdmin, SendVerificationConfigForm
from apps.authn.tests.services.send_verification.policy.test_send_verification_config import (
    INHERIT_SETTINGS,
    _SendVerificationConfigCase,
)
from apps.core.models import SendVerificationConfig


@override_settings(**INHERIT_SETTINGS)
class SendVerificationConfigTests(_SendVerificationConfigCase):
    def test_admin_shows_effective_policy_and_sources_without_exposing_secrets(self):
        model_admin = SendVerificationConfigAdmin(SendVerificationConfig, AdminSite())
        with override_settings(SEND_VERIFICATION_COST=950):
            display = str(model_admin.effective_configuration(self.config))
        self.assertIn("enforce", display)
        self.assertIn("950", display)
        self.assertIn("Django settings: SEND_VERIFICATION_COST", display)
        self.assertIn("Active database configuration: mode", display)
        self.assertIn("Configured", display)
        self.assertNotIn(self.config.hmac_secret, display)
        self.assertNotIn(self.config.hmac_key_secret, display)

    @override_settings(SEND_VERIFICATION_COST="bad")
    def test_admin_explains_invalid_effective_policy(self):
        model_admin = SendVerificationConfigAdmin(SendVerificationConfig, AdminSite())
        display = str(model_admin.effective_configuration(self.config))
        self.assertIn("protected sends are blocked", display)
        self.assertNotIn(self.config.hmac_secret, display)

    def test_admin_rejects_unsupported_algorithm_and_unsafe_numeric_policy(self):
        data = {name: getattr(self.config, name) for name in SendVerificationConfigForm.Meta.fields}
        for field, value in (
            ("algorithm", "invalid"),
            ("cost", 0),
            ("challenge_ttl_seconds", 29),
            ("destination_hourly_limit", 0),
        ):
            with self.subTest(field=field):
                form = SendVerificationConfigForm(data={**data, field: value}, instance=self.config)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
