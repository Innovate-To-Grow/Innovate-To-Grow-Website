"""Fixtures for the API-key provider runtime tests: a provider with a key in the in-memory credential store, and a
fake ``litellm.acompletion`` that records the real call kwargs without any network access."""

import os
from contextlib import contextmanager

from apps.core.services.credential_store import memory
from apps.system_intelligence.models import LLMProviderConfig
from apps.system_intelligence.services.agents.providers.keys import install_api_key

TEST_API_KEY = "sk-test-provider-key-1234"
AWS_ENV_KEYS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION_NAME", "AWS_REGION", "AWS_DEFAULT_REGION")
PROVIDER_ENV_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY")


class ProviderStoreMixin:
    """An empty in-memory credential store around every test."""

    def setUp(self):
        super().setUp()
        memory.reset()
        self.addCleanup(memory.reset)


def make_provider(*, name="DeepSeek", preset="deepseek", enabled=True, with_key=True, **fields):
    """A saved provider; with *with_key* its API key is installed in the (memory) credential store."""
    provider = LLMProviderConfig.objects.create(name=name, preset=preset, **fields)
    if with_key:
        install_api_key(provider, TEST_API_KEY)
    if enabled:
        provider.is_enabled = True
        provider.save(update_fields=["is_enabled", "updated_at"])
    return provider


class StopCall(Exception):
    """Raised by the fake acompletion once it has captured the call."""


@contextmanager
def capture_acompletion():
    """Swap ``litellm.acompletion`` for a recorder and clear AWS/provider env vars; restore both afterwards."""
    import litellm

    calls: list[dict] = []

    async def fake_acompletion(*args, **kwargs):
        calls.append(kwargs)
        raise StopCall("captured")

    original = litellm.acompletion
    removed = {key: os.environ.pop(key, None) for key in (*AWS_ENV_KEYS, *PROVIDER_ENV_KEYS)}
    litellm.acompletion = fake_acompletion
    try:
        yield calls
    finally:
        litellm.acompletion = original
        for key, value in removed.items():
            if value is not None:
                os.environ[key] = value


def assert_env_untouched(test_case):
    for key in (*AWS_ENV_KEYS, *PROVIDER_ENV_KEYS):
        test_case.assertNotIn(key, os.environ)
