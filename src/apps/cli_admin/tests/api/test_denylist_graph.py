from apps.cli_admin.models import CliAuditLog
from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff, make_superuser
from apps.core.models import MicrosoftGraphCertificate, MicrosoftGraphProviderConfig
from apps.core.tests.graph_helpers import create_graph_config

# Graph senders used in this module; the mailbox scope rules have their own tests.
GRAPH_TEST_SCOPE = ("sender@example.com",)

ATTACKER_VALUE = "attacker-chosen"
CONFIG_COLLECTION = "/admin-api/records/core/microsoftgraphproviderconfig/"
CERTIFICATE_COLLECTION = "/admin-api/records/core/microsoftgraphcertificate/"
DENIED = "{access} access is not allowed for core.{model}."


class GraphDenylistTests(CliApiTestCase):
    """The Graph config and its installed certificates are unreachable through /admin-api/, even for superusers."""

    def setUp(self):
        super().setUp()
        self.config = create_graph_config(
            scope=GRAPH_TEST_SCOPE,
            name="Mail",
            is_active=True,
            tenant_id="11111111-2222-3333-4444-555555555555",
            client_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            mailbox="sender@example.com",
        )
        self.certificate = self.config.current_certificate
        self.targets = {
            "MicrosoftGraphProviderConfig": (CONFIG_COLLECTION, f"{CONFIG_COLLECTION}{self.config.pk}/"),
            "MicrosoftGraphCertificate": (CERTIFICATE_COLLECTION, f"{CERTIFICATE_COLLECTION}{self.certificate.pk}/"),
        }
        # Both actors hold the "core" app grant (superusers hold every grant), so a 400 below comes from the
        # denylist and not from the per-app 403.
        self.actors = {
            "staff": self.auth(issue_token(make_staff(email="graph-staff@example.com"))[1]),
            "superuser": self.auth(issue_token(make_superuser(email="graph-admin@example.com"))[1]),
        }

    def assert_denied(self, response, access, model):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "bad_request")
        self.assertEqual(response.data["detail"], DENIED.format(access=access, model=model))
        self.assertNotIn(self.certificate.store_version_id, response.content.decode())

    def each_target(self):
        for actor, auth in self.actors.items():
            for model, (collection, detail) in self.targets.items():
                with self.subTest(actor=actor, model=model):
                    yield auth, model, collection, detail

    def test_reads_and_schemas_are_400(self):
        for auth, model, collection, detail in self.each_target():
            self.assert_denied(self.client.get(collection, **auth), "Read", model)
            self.assert_denied(self.client.get(collection, {"count": "1"}, **auth), "Read", model)
            self.assert_denied(self.client.get(detail, **auth), "Read", model)
            schema = f"/admin-api/models/core/{model.lower()}/schema/"
            self.assert_denied(self.client.get(schema, **auth), "Read", model)

    def test_filtering_is_refused_rather_than_used_as_an_oracle(self):
        query = {"filter": f"store_version_id={self.certificate.store_version_id}", "field": "store_version_id"}
        for auth, model, collection, _detail in self.each_target():
            self.assert_denied(self.client.get(collection, query, **auth), "Read", model)

    def test_model_catalogue_omits_the_models(self):
        for actor, auth in self.actors.items():
            with self.subTest(actor=actor):
                response = self.client.get("/admin-api/models/", **auth)

                self.assertEqual(response.status_code, 200)
                labels = {row["label"] for row in response.data}
                self.assertIn("projects.Semester", labels)
                self.assertNotIn("core.MicrosoftGraphProviderConfig", labels)
                self.assertNotIn("core.MicrosoftGraphCertificate", labels)

    def test_create_is_400_and_writes_nothing(self):
        payload = {"name": "Injected", "tenant_id": "contoso.com", "client_id": "x", "state": "current"}
        for auth, model, collection, _detail in self.each_target():
            self.assert_denied(self.client.post(collection, payload, format="json", **auth), "Write", model)

        self.assertEqual(MicrosoftGraphProviderConfig.objects.count(), 1)
        self.assertEqual(MicrosoftGraphCertificate.objects.count(), 1)

    def test_update_is_400_and_leaves_the_rows_untouched(self):
        changes = (("mailbox", "attacker@example.com"), ("state", "removed"), ("store_version_id", ATTACKER_VALUE))
        for auth, model, _collection, detail in self.each_target():
            for field, value in changes:
                response = self.client.patch(detail, {field: value}, format="json", **auth)
                self.assert_denied(response, "Write", model)

        self.config.refresh_from_db()
        self.certificate.refresh_from_db()
        self.assertEqual(self.config.mailbox, "sender@example.com")
        self.assertEqual(self.certificate.state, MicrosoftGraphCertificate.State.CURRENT)
        self.assertNotEqual(self.certificate.store_version_id, ATTACKER_VALUE)

    def test_delete_is_400_and_keeps_the_rows(self):
        for auth, model, _collection, detail in self.each_target():
            self.assert_denied(self.client.delete(detail, **auth), "Write", model)
            self.assert_denied(self.client.delete(f"{detail}?confirm_cascade=1", **auth), "Write", model)

        self.assertTrue(MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).exists())
        self.assertTrue(MicrosoftGraphCertificate.objects.filter(pk=self.certificate.pk).exists())

    def test_denied_writes_are_audited_as_failed(self):
        detail = self.targets["MicrosoftGraphCertificate"][1]
        response = self.client.patch(
            detail, {"store_version_id": ATTACKER_VALUE}, format="json", **self.actors["staff"]
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(CliAuditLog.objects.filter(status="success").exists())
        log = CliAuditLog.objects.get(action="update", status="failed")
        self.assertEqual(log.model_name, "microsoftgraphcertificate")
        for stored in (log.error_message, log.target_repr, str(log.changes), str(log.before_snapshot)):
            self.assertNotIn(ATTACKER_VALUE, stored)
