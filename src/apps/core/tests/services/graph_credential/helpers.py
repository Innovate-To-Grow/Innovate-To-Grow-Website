"""Fixtures for the certificate lifecycle tests: parsed certificates, Entra answers and a clean key store."""

import json

from apps.core.services.credential_store import memory, secret_id_for
from apps.core.services.email.graph.certificate import describe_certificate
from apps.core.services.email.graph.credential import stored_key
from apps.core.services.email.graph.credential.parsing import ParsedCertificate
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import make_certificate
from apps.core.tests.services.test_email_graph import GraphFixtureMixin
from apps.event.tests.helpers import make_superuser as make_superuser  # re-exported for the lifecycle tests


def parsed_certificate(*, with_key=True, **certificate_options):
    """A validated certificate as ``parse_certificate_input`` returns it, and its key."""
    certificate, key = make_certificate(**certificate_options)
    return ParsedCertificate(facts=describe_certificate(certificate), private_key=key if with_key else None), key


def entra_rejection(number, error="invalid_client"):
    body = {"error": error, "error_codes": [number], "error_description": f"AADSTS{number}: free text"}
    return HttpResponse(401, {}, json.dumps(body).encode())


def stored_versions() -> dict:
    """Every key version in the in-memory store, labelled or not."""
    return dict(memory._versions.get(secret_id_for(stored_key.KEY_NAME), {}))


class LifecycleFixtureMixin(GraphFixtureMixin):
    """An empty key store and the faked identity platform (``self.fake``, from ``GraphFixtureMixin``)."""

    def setUp(self):
        super().setUp()
        memory.reset()
        self.addCleanup(memory.reset)
