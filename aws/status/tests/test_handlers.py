from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from status_service import handlers
from status_service.constants import COMPONENTS
from status_service.types import ProbeOutcome


class Repository:
    def __init__(self):
        self.completed_slots = set()
        self.currents = {}
        self.finished = []
        self.snapshots = []

    def begin_run(self, slot, _generated_at):
        return slot not in self.completed_slots

    def get_current(self, component_id):
        return self.currents.get(component_id)

    def save_transition(self, transition):
        self.currents[transition.component_id] = transition.current
        return True

    def put_system_snapshots(self, generated_at, slot_at, public, detail):
        self.snapshots.append((generated_at, slot_at, public, detail))
        return True

    def finish_run(self, slot, state, _generated_at):
        self.finished.append((slot, state))
        if state == "COMPLETE":
            self.completed_slots.add(slot)


class Engine:
    def run(self):
        outcomes = {
            component.component_id: ProbeOutcome(
                component.component_id,
                "healthy",
                "available",
                False,
                10,
                (),
            )
            for component in COMPONENTS
        }
        return outcomes, {
            "probes": [],
            "alarms": {"state": "ok", "alarms": []},
            "stack": {
                "state": "ok",
                "name": "i2g-status",
                "stackStatus": "UPDATE_COMPLETE",
                "resources": [],
            },
        }


class Metrics:
    def __init__(self, fail=False):
        self.values = []
        self.fail = fail

    def success(self, value):
        self.values.append(value)
        if self.fail:
            raise RuntimeError("metrics unavailable")


def test_scheduler_retry_uses_original_slot_across_wall_clock_boundary(settings_factory):
    repository = Repository()
    slot_at = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)

    first = handlers.run_probe(
        now=datetime(2026, 8, 20, 10, 4, tzinfo=UTC),
        slot_at=slot_at,
        settings=settings_factory(),
        repository=repository,
        engine=Engine(),
        metric_writer=Metrics(),
    )
    retry = handlers.run_probe(
        now=datetime(2026, 8, 20, 10, 11, tzinfo=UTC),
        slot_at=slot_at,
        settings=settings_factory(),
        repository=repository,
        engine=Engine(),
        metric_writer=Metrics(),
    )

    assert first["slot"] == "20260820T1000Z"
    assert retry == {"status": "duplicate", "slot": "20260820T1000Z"}


@pytest.mark.parametrize(
    "slot_at",
    [
        datetime(2026, 8, 20, 10, 2, tzinfo=UTC),
        datetime(2026, 8, 20, 9, 39, tzinfo=UTC),
    ],
)
def test_scheduler_timestamp_is_bounded(slot_at, settings_factory):
    with pytest.raises(ValueError, match="outside"):
        handlers.run_probe(
            now=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
            slot_at=slot_at,
            settings=settings_factory(),
            repository=Repository(),
            engine=Engine(),
            metric_writer=Metrics(),
        )


def test_metric_failure_never_changes_committed_probe_outcome(settings_factory):
    repository = Repository()

    result = handlers.run_probe(
        now=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        settings=settings_factory(),
        repository=repository,
        engine=Engine(),
        metric_writer=Metrics(fail=True),
    )

    assert result["status"] == "complete"
    assert repository.finished == [("20260820T1000Z", "COMPLETE")]


def test_metric_client_creation_failure_never_changes_probe_outcome(monkeypatch, settings_factory):
    repository = Repository()
    monkeypatch.setattr(
        handlers,
        "_CloudWatchMetrics",
        lambda _region: (_ for _ in ()).throw(RuntimeError("metrics client unavailable")),
    )

    result = handlers.run_probe(
        now=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        settings=settings_factory(),
        repository=repository,
        engine=Engine(),
    )

    assert result["status"] == "complete"


def test_probe_handler_raises_only_fixed_sanitized_failure(monkeypatch, caplog):
    monkeypatch.setattr(
        handlers,
        "run_probe",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("arn:aws:secret account 123456789012")),
    )

    with pytest.raises(RuntimeError, match="^STATUS_PROBE_FAILED$") as raised:
        handlers.probe_handler({"time": "2026-08-20T10:00:00Z"}, None)

    assert raised.value.__cause__ is None
    assert "123456789012" not in caplog.text


def test_read_handlers_require_only_table_environment(monkeypatch):
    monkeypatch.setenv("STATUS_TABLE_NAME", "table-only")
    monkeypatch.delenv("PRODUCTION_TARGET_GROUP_ARN", raising=False)
    seen = []

    class ReadRepository:
        def __init__(self, table_name):
            seen.append(table_name)

        def get_system(self, kind):
            assert kind == "DETAIL"
            return {
                "generatedAt": "2026-08-20T10:00:00Z",
                "partial": False,
                "errors": [],
                "stack": {"name": "i2g-status", "resources": []},
                "services": [],
                "probes": [],
                "alarms": [],
            }

    monkeypatch.setattr(handlers, "StatusRepository", ReadRepository)
    monkeypatch.setattr(
        handlers,
        "build_public_snapshot",
        lambda _repository: {"schemaVersion": 1},
    )

    public = handlers.public_read_handler({}, None)
    internal = handlers.internal_read_handler({}, None)

    assert public["statusCode"] == 200
    assert json.loads(public["body"])["schemaVersion"] == 1
    assert internal["statusCode"] == 200
    internal_body = json.loads(internal["body"])
    assert set(internal_body) == {
        "schemaVersion",
        "generatedAt",
        "partial",
        "errors",
        "stack",
        "services",
        "probes",
        "alarms",
    }
    assert seen == ["table-only", "table-only"]
