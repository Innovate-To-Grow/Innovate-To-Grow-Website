from decimal import Decimal

from django.utils import timezone

from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff, make_superuser
from apps.core.models import DeliveryRateLimit, DeliveryRatePolicy, DeliveryRateState, DeliveryUsageBucket

DENIED = "{access} access is not allowed for core.{model}."
COLLECTION = "/admin-api/records/core/{model}/"


class DeliveryRateDenylistTests(CliApiTestCase):
    """The delivery-rate policy, its live state and usage, and the legacy rate slot are unreachable through
    /admin-api/, even for superusers: rates are changed on Mail → Delivery Rates only."""

    def setUp(self):
        super().setUp()
        DeliveryRatePolicy.objects.all().delete()
        self.policy = DeliveryRatePolicy.for_channel(DeliveryRatePolicy.Channel.SMS_SEND)
        self.state = DeliveryRateState.objects.create(
            channel=DeliveryRatePolicy.Channel.SMS_SEND,
            identity="us-west-2:+12095550100",
            cooldown_group="sms:us-west-2",
        )
        self.bucket = DeliveryUsageBucket.objects.create(state=self.state, bucket_start=timezone.now(), total=1)
        self.slot = DeliveryRateLimit.objects.create(provider="ses")
        self.targets = {
            "DeliveryRatePolicy": self.policy.pk,
            "DeliveryRateState": self.state.pk,
            "DeliveryUsageBucket": self.bucket.pk,
            "DeliveryRateLimit": self.slot.pk,
        }
        # Both actors hold the "core" app grant (superusers hold every grant), so a 400 below comes from the
        # denylist and not from the per-app 403.
        self.actors = {
            "staff": self.auth(issue_token(make_staff(email="rates-staff@example.com"))[1]),
            "superuser": self.auth(issue_token(make_superuser(email="rates-admin@example.com"))[1]),
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
            self.assert_denied(self.client.get(collection, {"filter": "channel=sms_send"}, **auth), "Read", model)
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
                collection, {"channel": "graph_send", "manual_rate": "999"}, format="json", **auth
            )
            self.assert_denied(create, "Write", model)
            update = self.client.patch(detail, {"manual_rate": "999", "smart_enabled": False}, format="json", **auth)
            self.assert_denied(update, "Write", model)
            self.assert_denied(self.client.delete(f"{detail}?confirm_cascade=1", **auth), "Write", model)

        self.policy.refresh_from_db()
        self.assertEqual((self.policy.manual_rate, self.policy.smart_enabled), (Decimal(1), True))
        self.assertEqual(DeliveryRatePolicy.objects.count(), 1)
        self.assertTrue(DeliveryUsageBucket.objects.filter(pk=self.bucket.pk).exists())
        self.assertTrue(DeliveryRateLimit.objects.filter(pk=self.slot.pk).exists())
