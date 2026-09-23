"""New challenge columns remain compatible with an older application writer."""

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase

from apps.authn.models import EmailAuthChallenge
from apps.event.tests.helpers import make_member


class EventEmailChallengeContextMigrationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_previous_model_can_insert_without_context_column(self):
        old_apps = (
            MigrationExecutor(connection)
            .loader.project_state([("authn", "0019_senddestinationstate_sendquotawindow_and_more")])
            .apps
        )
        old_challenge = old_apps.get_model("authn", "EmailAuthChallenge")
        member = make_member()
        inserted = old_challenge.objects.create(
            member_id=member.pk,
            purpose="login",
            target_email="legacy@example.com",
            code_hash=make_password("123456"),
            expires_at=EmailAuthChallenge.default_expiry(),
        )
        self.assertEqual(EmailAuthChallenge.objects.get(pk=inserted.pk).context_identifier, "")
