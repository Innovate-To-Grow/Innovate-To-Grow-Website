import importlib
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase

normalize_active_schedule = importlib.import_module(
    "apps.event.migrations.0010_active_schedule_invariant"
).normalize_active_schedule


class ActiveScheduleMigrationTest(SimpleTestCase):
    def test_keeps_the_same_row_as_the_legacy_first_loader(self):
        legacy_winner = SimpleNamespace(pk=uuid.UUID(int=1))
        active = Mock()
        ordered = Mock()
        ordered.first.return_value = legacy_winner
        active.order_by.return_value = ordered
        model = SimpleNamespace(objects=Mock())
        model.objects.filter.return_value = active
        historical_apps = Mock()
        historical_apps.get_model.return_value = model

        normalize_active_schedule(historical_apps, None)

        active.order_by.assert_called_once_with("pk")
        ordered.exclude.assert_called_once_with(pk=legacy_winner.pk)
        ordered.exclude.return_value.update.assert_called_once_with(is_active=False)
