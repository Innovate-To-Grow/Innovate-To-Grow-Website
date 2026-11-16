from django.test import SimpleTestCase

from apps.core.services.email import PermanentEmailDeliveryError
from apps.core.tests.graph_helpers import private_key_lines
from apps.core.tests.services.graph.provider.test_email_graph import make_provider


class GraphProviderConfigurationTests(SimpleTestCase):
    def test_provider_is_named_graph(self):
        self.assertEqual(make_provider().name, "graph")

    def test_accepts_domain_tenants_and_mailbox_object_ids(self):
        provider = make_provider(tenant_id="contoso.onmicrosoft.com", mailbox="72f988bf-86f1-41af-91ab-2d7cd011db47")

        self.assertEqual(provider.credential.tenant_id, "contoso.onmicrosoft.com")
        self.assertEqual(provider.mailbox, "72f988bf-86f1-41af-91ab-2d7cd011db47")

    def test_rejects_invalid_configuration_without_echoing_key_material(self):
        invalid = {
            "tenant without a dot": {"tenant_id": "common"},
            "tenant with a path separator": {"tenant_id": "a/b"},
            "blank tenant": {"tenant_id": ""},
            "client id that is not a guid": {"client_id": "not-a-guid"},
            "blank client id": {"client_id": ""},
            "mailbox that is not an address": {"mailbox": "not a mailbox"},
            "mailbox with an injected header": {"mailbox": "user@contoso.com\nBcc: evil@example.com"},
            "blank mailbox": {"mailbox": ""},
            "blank certificate thumbprint": {"x5t_s256": ""},
            "blank key reference": {"key_arn": ""},
            "blank key version": {"key_version_id": ""},
        }
        for label, overrides in invalid.items():
            with self.subTest(label):
                with self.assertRaisesMessage(PermanentEmailDeliveryError, "configuration is invalid") as caught:
                    make_provider(**overrides)
                for line in private_key_lines():
                    self.assertNotIn(line, str(caught.exception))

    def test_repr_does_not_expose_key_material(self):
        text = repr(make_provider())

        self.assertNotIn("PRIVATE KEY", text)
        for line in private_key_lines():
            self.assertNotIn(line, text)
