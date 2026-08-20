from __future__ import annotations

from types import SimpleNamespace

from botocore.exceptions import ClientError
from status_service.repository import StatusRepository
from status_service.types import IncidentMutation, StateTransition


class Client:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def transact_write_items(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error


class Table:
    def __init__(self, client):
        self.meta = SimpleNamespace(client=client)


def transition():
    return StateTransition(
        component_id="production-api",
        checked_at="2026-08-20T10:00:00Z",
        public_status="degraded",
        availability="unavailable",
        latency_ms=25,
        current={
            "componentId": "production-api",
            "name": "Production API",
            "group": "production",
            "status": "degraded",
            "checkedAt": "2026-08-20T10:00:00Z",
        },
        incident_mutations=(),
    )


def canceled(index):
    reasons = [{"Code": "None"}, {"Code": "None"}, {"Code": "None"}]
    reasons[index] = {"Code": "ConditionalCheckFailed"}
    return ClientError(
        {"Error": {"Code": "TransactionCanceledException", "Message": "cancelled"}, "CancellationReasons": reasons},
        "TransactWriteItems",
    )


def test_sample_rollup_and_current_are_one_transaction_with_ordering_condition():
    client = Client()
    repository = StatusRepository("status-table", table=Table(client))

    assert repository.save_transition(transition()) is True

    actions = client.calls[0]["TransactItems"]
    assert len(actions) == 3
    assert "attribute_not_exists(PK)" in actions[0]["Put"]["ConditionExpression"]
    daily = actions[1]["Update"]
    assert "ADD scheduledCount" in daily["UpdateExpression"]
    assert daily["ExpressionAttributeNames"]["#availability"] == "unavailableCount"
    assert daily["ExpressionAttributeNames"]["#status"] == "statusDegradedCount"
    current = actions[2]["Put"]
    assert current["ConditionExpression"] == "attribute_not_exists(PK) OR checkedAt < :checkedAt"
    assert ":zero" not in daily["ExpressionAttributeValues"]


def test_duplicate_sample_and_late_older_current_are_safe_noops():
    duplicate = StatusRepository("status-table", table=Table(Client(canceled(0))))
    delayed = StatusRepository("status-table", table=Table(Client(canceled(2))))

    assert duplicate.save_transition(transition()) is False
    assert delayed.save_transition(transition()) is False


def test_system_public_and_internal_snapshots_are_atomic_and_slot_ordered():
    client = Client()
    repository = StatusRepository("status-table", table=Table(client))

    saved = repository.put_system_snapshots(
        "2026-08-20T10:01:00Z",
        "2026-08-20T10:00:00Z",
        {"releaseSha": "abc"},
        {"schemaVersion": 1, "partial": False},
    )

    assert saved is True
    actions = client.calls[0]["TransactItems"]
    assert len(actions) == 2
    assert [action["Put"]["Item"]["PK"]["S"] for action in actions] == ["PUBLIC", "INTERNAL"]
    assert all(
        action["Put"]["ConditionExpression"] == "attribute_not_exists(PK) OR slotAt < :slotAt" for action in actions
    )


def test_system_reads_are_routed_to_isolated_partition_keys():
    class ReadTable(Table):
        def __init__(self, client):
            super().__init__(client)
            self.keys = []

        def get_item(self, **kwargs):
            self.keys.append(kwargs["Key"])
            return {"Item": {"generatedAt": "2026-08-20T10:00:00Z"}}

    table = ReadTable(Client())
    repository = StatusRepository("status-table", table=table)

    repository.get_system("CURRENT")
    repository.get_system("DETAIL")

    assert table.keys == [
        {"PK": "PUBLIC", "SK": "CURRENT"},
        {"PK": "INTERNAL", "SK": "DETAIL"},
    ]


def test_delayed_system_snapshot_cannot_replace_newer_pair():
    client = Client(canceled(0))
    repository = StatusRepository("status-table", table=Table(client))

    assert (
        repository.put_system_snapshots(
            "2026-08-20T10:10:30Z",
            "2026-08-20T09:55:00Z",
            {},
            {},
        )
        is False
    )


def test_incident_timeline_is_embedded_in_metadata_for_bounded_public_reads():
    repository = StatusRepository("status-table", table=Table(Client()))
    opened = IncidentMutation(
        action="open",
        incident_id="incident-production-api-20260820100000",
        kind="incident",
        state="investigating",
        at="2026-08-20T10:05:00Z",
        started_at="2026-08-20T10:00:00Z",
        impact="major_outage",
        component_id="production-api",
    )
    monitoring = IncidentMutation(
        action="update",
        incident_id=opened.incident_id,
        kind="incident",
        state="monitoring",
        at="2026-08-20T10:10:00Z",
        started_at=opened.started_at,
        impact="major_outage",
        component_id="production-api",
        opened_at="2026-08-20T10:05:00Z",
        monitoring_at="2026-08-20T10:10:00Z",
    )
    resolved = IncidentMutation(
        action="resolve",
        incident_id=opened.incident_id,
        kind="incident",
        state="resolved",
        at="2026-08-20T10:15:00Z",
        started_at=opened.started_at,
        impact="major_outage",
        component_id="production-api",
        opened_at="2026-08-20T10:05:00Z",
        monitoring_at="2026-08-20T10:10:00Z",
    )

    open_meta = repository._incident_actions(opened)[0]["Put"]["Item"]  # noqa: SLF001
    update_meta = repository._incident_actions(monitoring)[0]["Update"]  # noqa: SLF001
    resolve_meta = repository._incident_actions(resolved)[0]["Update"]  # noqa: SLF001

    assert open_meta["updates"]["L"][0]["M"]["state"]["S"] == "investigating"
    assert "list_append" not in update_meta["UpdateExpression"]
    assert [item["M"]["state"]["S"] for item in update_meta["ExpressionAttributeValues"][":updates"]["L"]] == [
        "investigating",
        "monitoring",
    ]
    assert [item["M"]["state"]["S"] for item in resolve_meta["ExpressionAttributeValues"][":updates"]["L"]] == [
        "investigating",
        "monitoring",
        "resolved",
    ]
