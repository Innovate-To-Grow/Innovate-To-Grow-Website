from apps.cli_admin.models import CliAuditLog
from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff, make_superuser
from apps.core.models import MicrosoftGraphProviderConfig

SECRET = "not-a-real-graph-secret"
ATTACKER_VALUE = "attacker-chosen"
COLLECTION = "/admin-api/records/core/microsoftgraphproviderconfig/"
SCHEMA = "/admin-api/models/core/microsoftgraphproviderconfig/schema/"
DENIED_READ = "Read access is not allowed for core.MicrosoftGraphProviderConfig."
DENIED_WRITE = "Write access is not allowed for core.MicrosoftGraphProviderConfig."


class GraphDenylistTests(CliApiTestCase):
    """Microsoft Graph credentials are unreachable through /admin-api/, even for superusers and the core app."""

    def setUp(self):
        super().setUp()
        self.config = MicrosoftGraphProviderConfig.objects.create(
            name="Mail",
            is_active=True,
            tenant_id="11111111-2222-3333-4444-555555555555",
            client_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            client_secret=SECRET,
            mailbox="sender@example.com",
        )
        self.detail = f"{COLLECTION}{self.config.pk}/"
        # Both actors hold the "core" app grant (superusers hold every grant), so a 400 below comes from the
        # denylist and not from the per-app 403.
        self.actors = {
            "staff": self.auth(issue_token(make_staff(email="graph-staff@example.com"))[1]),
            "superuser": self.auth(issue_token(make_superuser(email="graph-admin@example.com"))[1]),
        }

    def assert_denied(self, response, detail):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "bad_request")
        self.assertEqual(response.data["detail"], detail)
        self.assertNotIn(SECRET, response.content.decode())

    def test_reads_are_400_and_never_return_the_secret(self):
        for actor, auth in self.actors.items():
            with self.subTest(actor=actor):
                self.assert_denied(self.client.get(COLLECTION, **auth), DENIED_READ)
                self.assert_denied(self.client.get(COLLECTION, {"count": "1"}, **auth), DENIED_READ)
                self.assert_denied(self.client.get(self.detail, **auth), DENIED_READ)

    def test_filtering_on_the_secret_is_refused_rather_than_used_as_an_oracle(self):
        query = {"filter": f"client_secret={SECRET}", "field": "client_secret"}
        for actor, auth in self.actors.items():
            with self.subTest(actor=actor):
                self.assert_denied(self.client.get(COLLECTION, query, **auth), DENIED_READ)

    def test_schema_is_400(self):
        for actor, auth in self.actors.items():
            with self.subTest(actor=actor):
                self.assert_denied(self.client.get(SCHEMA, **auth), DENIED_READ)

    def test_model_catalogue_omits_the_model(self):
        for actor, auth in self.actors.items():
            with self.subTest(actor=actor):
                response = self.client.get("/admin-api/models/", **auth)

                self.assertEqual(response.status_code, 200)
                labels = {row["label"] for row in response.data}
                self.assertIn("projects.Semester", labels)
                self.assertNotIn("core.MicrosoftGraphProviderConfig", labels)

    def test_create_is_400_and_writes_nothing(self):
        payload = {"name": "Injected", "tenant_id": "contoso.com", "client_id": "x", "client_secret": ATTACKER_VALUE}
        for actor, auth in self.actors.items():
            with self.subTest(actor=actor):
                self.assert_denied(self.client.post(COLLECTION, payload, format="json", **auth), DENIED_WRITE)

        self.assertEqual(MicrosoftGraphProviderConfig.objects.count(), 1)

    def test_update_is_400_and_leaves_the_row_untouched(self):
        changes = (("mailbox", "attacker@example.com"), ("client_secret", ATTACKER_VALUE), ("is_active", False))
        for actor, auth in self.actors.items():
            for field, value in changes:
                with self.subTest(actor=actor, field=field):
                    response = self.client.patch(self.detail, {field: value}, format="json", **auth)

                    self.assert_denied(response, DENIED_WRITE)

        self.config.refresh_from_db()
        self.assertEqual(self.config.mailbox, "sender@example.com")
        self.assertEqual(self.config.client_secret, SECRET)
        self.assertTrue(self.config.is_active)

    def test_delete_is_400_and_keeps_the_row(self):
        for actor, auth in self.actors.items():
            with self.subTest(actor=actor):
                self.assert_denied(self.client.delete(self.detail, **auth), DENIED_WRITE)
                self.assert_denied(self.client.delete(f"{self.detail}?confirm_cascade=1", **auth), DENIED_WRITE)

        self.assertTrue(MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).exists())

    def test_denied_writes_are_audited_as_failed_without_any_secret(self):
        response = self.client.patch(
            self.detail, {"client_secret": ATTACKER_VALUE}, format="json", **self.actors["staff"]
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(CliAuditLog.objects.filter(status="success").exists())
        log = CliAuditLog.objects.get(action="update", status="failed")
        self.assertEqual(log.model_name, "microsoftgraphproviderconfig")
        for stored in (log.error_message, log.target_repr, str(log.changes), str(log.before_snapshot)):
            self.assertNotIn(SECRET, stored)
            self.assertNotIn(ATTACKER_VALUE, stored)
