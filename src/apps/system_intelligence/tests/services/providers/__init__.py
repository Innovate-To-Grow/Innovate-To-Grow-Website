"""Tests for the non-Bedrock AI provider services and the ``LLMProviderConfig`` model."""

from django.utils import timezone

from apps.system_intelligence.models import LLMProviderConfig


def make_provider(**overrides):
    """Save an ``LLMProviderConfig`` (DeepSeek preset, no key, disabled unless overridden)."""
    fields = {"name": "DeepSeek", "preset": LLMProviderConfig.Preset.DEEPSEEK}
    fields.update(overrides)
    return LLMProviderConfig.objects.create(**fields)


def make_keyed_provider(**overrides):
    """``make_provider`` with a (fake) pinned key and enabled, for tests that never read the key."""
    fields = {
        "key_secret_ref": "memory:itg/backend/system-intelligence/llm-api-key",
        "key_version_id": "0" * 32,
        "key_hint": "abcd",
        "key_installed_at": timezone.now(),
        "is_enabled": True,
    }
    fields.update(overrides)
    return make_provider(**fields)
