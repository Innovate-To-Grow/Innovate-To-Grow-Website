from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff, make_superuser
from apps.core.tests.gmail_api_helpers import make_config

DENIED = "{access} access is not allowed for core.{model}."
COLLECTION = "/admin-api/records/core/{model}/"


class GmailApiDenylistTests(CliApiTestCase):
    """The Gmail API config (key pointer and facts) and its subject allow-list are unreachable through /admin-api/,
    even for superusers: they are managed on the superuser-only admin pages."""

    def setUp(self):
        super().setUp()
        config = make_config()
        self.targets = {"GmailApiProviderConfig": config.pk, "GmailApiSubject": config.subjects.get().pk}
        self.actors = {
            "staff": self.auth(issue_token(make_staff(email="gmail-staff@example.com"))[1]),
            "superuser": self.auth(issue_token(make_superuser(email="gmail-admin@example.com"))[1]),
        }

    def assert_denied(self, response, access, model):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], DENIED.format(access=access, model=model))

    def test_reads_writes_and_the_catalogue_refuse_both_models(self):
        for actor, auth in self.actors.items():
            labels = {row["label"] for row in self.client.get("/admin-api/models/", **auth).data}
            for model, pk in self.targets.items():
                with self.subTest(actor=actor, model=model):
                    collection = COLLECTION.format(model=model.lower())
                    detail = f"{collection}{pk}/"
                    self.assertNotIn(f"core.{model}", labels)
                    self.assert_denied(self.client.get(collection, **auth), "Read", model)
                    self.assert_denied(self.client.get(detail, **auth), "Read", model)
                    filtered = self.client.get(collection, {"filter": "subject=i2g@g.ucmerced.edu"}, **auth)
                    self.assert_denied(filtered, "Read", model)
                    created = self.client.post(collection, {"subject": "x@g.ucmerced.edu"}, format="json", **auth)
                    self.assert_denied(created, "Write", model)
                    self.assert_denied(self.client.patch(detail, {"name": "x"}, format="json", **auth), "Write", model)
                    self.assert_denied(self.client.delete(detail, **auth), "Write", model)
