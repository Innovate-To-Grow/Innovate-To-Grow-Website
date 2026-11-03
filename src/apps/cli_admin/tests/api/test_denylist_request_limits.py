from django.core.cache import cache
from django.utils import timezone

from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff, make_superuser
from apps.core.models import RequestLimitProcess, RequestRateLimitPolicy, RequestRateLimitState

DENIED = "{access} access is not allowed for core.{model}."
COLLECTION = "/admin-api/records/core/{model}/"


class RequestLimitDenylistTests(CliApiTestCase):
    """The request-limit policies, their Smart state and the process heartbeats are unreachable through /admin-api/,
    even for superusers: limits are changed on Site Settings → Request Limits only, where every change is audited."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.policy = RequestRateLimitPolicy.for_scope("auth-code-send")
        self.state, _created = RequestRateLimitState.objects.get_or_create(scope="auth-code-send")
        now = timezone.now()
        self.process = RequestLimitProcess.objects.create(instance="cli-test", pid=1, started_at=now, last_seen=now)
        self.targets = {
            "RequestRateLimitPolicy": self.policy.pk,
            "RequestRateLimitState": self.state.pk,
            "RequestLimitProcess": self.process.pk,
        }
        # Both actors hold the "core" app grant (superusers hold every grant), so a 400 below comes from the
        # denylist and not from the per-app 403.
        self.actors = {
            "staff": self.auth(issue_token(make_staff(email="limits-staff@example.com"))[1]),
            "superuser": self.auth(issue_token(make_superuser(email="limits-admin@example.com"))[1]),
        }

    def assert_denied(self, response, access, model):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "bad_request")
        self.assertEqual(response.data["detail"], DENIED.format(access=access, model=model))

    def each_target(self):
        for actor, auth in self.actors.items():
            for model, pk in self.targets.items():
                with self.subTest(actor=actor, model=model):
                    collection = COLLECTION.format(model=model.lower())
                    yield auth, model, collection, f"{collection}{pk}/"

    def test_reads_filters_and_schemas_are_400(self):
        for auth, model, collection, detail in self.each_target():
            self.assert_denied(self.client.get(collection, **auth), "Read", model)
            self.assert_denied(self.client.get(collection, {"filter": "scope=auth-code-send"}, **auth), "Read", model)
            self.assert_denied(self.client.get(detail, **auth), "Read", model)
            schema = f"/admin-api/models/core/{model.lower()}/schema/"
            self.assert_denied(self.client.get(schema, **auth), "Read", model)

    def test_model_catalogue_omits_the_models(self):
        for actor, auth in self.actors.items():
            with self.subTest(actor=actor):
                response = self.client.get("/admin-api/models/", **auth)

                self.assertEqual(response.status_code, 200)
                labels = {row["label"] for row in response.data}
                self.assertIn("projects.Semester", labels)
                for model in self.targets:
                    self.assertNotIn(f"core.{model}", labels)

    def test_writes_are_400_and_change_nothing(self):
        for auth, model, collection, detail in self.each_target():
            create = self.client.post(
                collection, {"scope": "ai", "manual_requests": 99_999, "label": "x"}, format="json", **auth
            )
            self.assert_denied(create, "Write", model)
            update = self.client.patch(
                detail, {"manual_requests": 99_999, "tier": "p3", "factor": 0.01}, format="json", **auth
            )
            self.assert_denied(update, "Write", model)
            self.assert_denied(self.client.delete(f"{detail}?confirm_cascade=1", **auth), "Write", model)

        self.policy.refresh_from_db()
        self.state.refresh_from_db()
        self.assertEqual((self.policy.manual_requests, self.policy.tier), (10, "p0"))
        self.assertEqual(self.state.factor, 1.0)
        self.assertTrue(RequestLimitProcess.objects.filter(pk=self.process.pk).exists())
