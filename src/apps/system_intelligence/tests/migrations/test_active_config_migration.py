import importlib
from datetime import timedelta

from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from apps.system_intelligence.models import SystemIntelligenceConfig


normalize_active_config = importlib.import_module(
    "apps.system_intelligence.migrations.0005_active_config_invariant"
).normalize_active_config


class ActiveConfigMigrationTest(TestCase):
    def test_promotes_the_legacy_latest_fallback_when_none_is_active(self):
        older = SystemIntelligenceConfig.objects.create(name="Older", is_active=False)
        newer = SystemIntelligenceConfig.objects.create(name="Newer", is_active=False)
        now = timezone.now()
        SystemIntelligenceConfig.objects.filter(pk=older.pk).update(updated_at=now - timedelta(days=1))
        SystemIntelligenceConfig.objects.filter(pk=newer.pk).update(updated_at=now)

        normalize_active_config(apps, None)

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertFalse(older.is_active)
        self.assertTrue(newer.is_active)
