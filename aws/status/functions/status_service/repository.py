"""DynamoDB persistence with per-slot idempotency and atomic rollups."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from .constants import HISTORY_TTL_SECONDS, RUN_TTL_SECONDS, SAMPLE_TTL_SECONDS
from .types import IncidentMutation, StateTransition


class StatusRepository:
    def __init__(self, table_name: str, *, table: Any | None = None):
        if table is None:
            import boto3

            table = boto3.resource("dynamodb").Table(table_name)
        self.table = table
        self.table_name = table_name
        self.client = table.meta.client
        self._serializer = TypeSerializer()

    def begin_run(self, slot: str, generated_at: str) -> bool:
        """Claim a slot, or resume it when a previous invocation was interrupted."""

        expires_at = _epoch(generated_at) + RUN_TTL_SECONDS
        try:
            self.table.put_item(
                Item={
                    "PK": f"RUN#{slot}",
                    "SK": "META",
                    "state": "PROCESSING",
                    "generatedAt": generated_at,
                    "expiresAt": expires_at,
                },
                ConditionExpression="attribute_not_exists(PK)",
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
        existing = self.table.get_item(Key={"PK": f"RUN#{slot}", "SK": "META"}, ConsistentRead=True).get("Item", {})
        return existing.get("state") != "COMPLETE"

    def finish_run(self, slot: str, state: str, generated_at: str) -> None:
        self.table.update_item(
            Key={"PK": f"RUN#{slot}", "SK": "META"},
            UpdateExpression="SET #state = :state, completedAt = :at",
            ExpressionAttributeNames={"#state": "state"},
            ExpressionAttributeValues={":state": state, ":at": generated_at},
        )

    def get_current(self, component_id: str) -> dict[str, Any] | None:
        item = self.table.get_item(
            Key={"PK": f"COMPONENT#{component_id}", "SK": "CURRENT"},
            ConsistentRead=True,
        ).get("Item")
        return _plain(item) if item else None

    def save_transition(self, transition: StateTransition) -> bool:
        """Atomically record a sample, its rollup, current state, and incident changes."""

        timestamp = transition.checked_at
        date = timestamp[:10]
        sample_ttl = _epoch(timestamp) + SAMPLE_TTL_SECONDS
        history_ttl = _epoch(f"{date}T00:00:00Z") + HISTORY_TTL_SECONDS
        component_pk = f"COMPONENT#{transition.component_id}"
        sample_item = {
            "PK": component_pk,
            "SK": f"SAMPLE#{timestamp}",
            "entityType": "sample",
            "componentId": transition.component_id,
            "checkedAt": timestamp,
            "status": transition.public_status,
            "availability": transition.availability,
            "latencyMs": transition.latency_ms,
            "expiresAt": sample_ttl,
        }
        current_item = {"PK": component_pk, "SK": "CURRENT", "entityType": "current", **transition.current}
        availability_counter = f"{transition.availability}Count"
        status_counter = f"status{_pascal(transition.public_status)}Count"
        values = {
            ":one": 1,
            ":updated": timestamp,
            ":ttl": history_ttl,
        }
        actions: list[dict[str, Any]] = [
            {
                "Put": {
                    "TableName": self.table_name,
                    "Item": self._item(sample_item),
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
            {
                "Update": {
                    "TableName": self.table_name,
                    "Key": self._item({"PK": component_pk, "SK": f"DAY#{date}"}),
                    "UpdateExpression": (
                        "SET entityType = :day, componentId = :component, #date = :date, "
                        "updatedAt = :updated, expiresAt = :ttl "
                        "ADD scheduledCount :one, #availability :one, #status :one"
                    ),
                    "ExpressionAttributeNames": {
                        "#date": "date",
                        "#availability": availability_counter,
                        "#status": status_counter,
                    },
                    "ExpressionAttributeValues": self._values(
                        {
                            **values,
                            ":day": "day",
                            ":component": transition.component_id,
                            ":date": date,
                        }
                    ),
                }
            },
            {
                "Put": {
                    "TableName": self.table_name,
                    "Item": self._item(current_item),
                    "ConditionExpression": "attribute_not_exists(PK) OR checkedAt < :checkedAt",
                    "ExpressionAttributeValues": self._values({":checkedAt": timestamp}),
                }
            },
        ]
        for mutation in transition.incident_mutations:
            actions.extend(self._incident_actions(mutation))
        try:
            self.client.transact_write_items(TransactItems=actions)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            cancellation_reasons = exc.response.get("CancellationReasons", [])
            expected_condition = any(
                index < len(cancellation_reasons)
                and cancellation_reasons[index].get("Code") == "ConditionalCheckFailed"
                for index in (0, 2)
            )
            if code == "ConditionalCheckFailedException" or expected_condition:
                return False
            raise

    def put_system_snapshots(
        self,
        generated_at: str,
        slot_at: str,
        public_current: dict[str, Any],
        detail: dict[str, Any],
    ) -> bool:
        """Replace the public/internal pair only when this scheduled slot is newer."""

        condition = "attribute_not_exists(PK) OR slotAt < :slotAt"
        values = self._values({":slotAt": slot_at})
        items = (
            {
                "PK": "PUBLIC",
                "SK": "CURRENT",
                "entityType": "public-system",
                "generatedAt": generated_at,
                "slotAt": slot_at,
                **public_current,
            },
            {
                "PK": "INTERNAL",
                "SK": "DETAIL",
                "entityType": "internal-system-detail",
                "generatedAt": generated_at,
                "slotAt": slot_at,
                **detail,
            },
        )
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": self._item(item),
                            "ConditionExpression": condition,
                            "ExpressionAttributeValues": values,
                        }
                    }
                    for item in items
                ]
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException" and any(
                reason.get("Code") == "ConditionalCheckFailed" for reason in exc.response.get("CancellationReasons", [])
            ):
                return False
            raise

    def get_system(self, kind: str) -> dict[str, Any] | None:
        normalized = kind.upper()
        keys = {
            "CURRENT": {"PK": "PUBLIC", "SK": "CURRENT"},
            "DETAIL": {"PK": "INTERNAL", "SK": "DETAIL"},
        }
        if normalized not in keys:
            raise ValueError("unsupported system snapshot kind")
        item = self.table.get_item(Key=keys[normalized], ConsistentRead=True).get("Item")
        return _plain(item) if item else None

    def list_days(self, component_id: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        return self._query_pk_range(
            f"COMPONENT#{component_id}",
            f"DAY#{start_date}",
            f"DAY#{end_date}",
        )

    def list_samples(self, component_id: str, start_at: str, end_at: str) -> list[dict[str, Any]]:
        return self._query_pk_range(
            f"COMPONENT#{component_id}",
            f"SAMPLE#{start_at}",
            f"SAMPLE#{end_at}",
        )

    def list_incidents(self, start_at: str) -> list[dict[str, Any]]:
        response = self.table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq("INCIDENTS") & Key("GSI1SK").gte(start_at),
            ScanIndexForward=False,
        )
        items = [_plain(item) for item in response.get("Items", [])]
        while response.get("LastEvaluatedKey"):
            response = self.table.query(
                IndexName="GSI1",
                KeyConditionExpression=Key("GSI1PK").eq("INCIDENTS") & Key("GSI1SK").gte(start_at),
                ScanIndexForward=False,
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(_plain(item) for item in response.get("Items", []))
        return items

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        item = self.table.get_item(Key={"PK": f"INCIDENT#{incident_id}", "SK": "META"}).get("Item")
        return _plain(item) if item else None

    def list_incident_updates(self, incident_id: str) -> list[dict[str, Any]]:
        return self._query_pk_range(f"INCIDENT#{incident_id}", "UPDATE#", "UPDATE#\uffff")

    def _query_pk_range(self, pk: str, start: str, end: str) -> list[dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression=Key("PK").eq(pk) & Key("SK").between(start, end),
            ScanIndexForward=True,
        )
        items = [_plain(item) for item in response.get("Items", [])]
        while response.get("LastEvaluatedKey"):
            response = self.table.query(
                KeyConditionExpression=Key("PK").eq(pk) & Key("SK").between(start, end),
                ScanIndexForward=True,
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(_plain(item) for item in response.get("Items", []))
        return items

    def _incident_actions(self, mutation: IncidentMutation) -> list[dict[str, Any]]:
        expires_at = _epoch(mutation.at) + HISTORY_TTL_SECONDS
        name = _component_name(mutation.component_id)
        meta_key = {"PK": f"INCIDENT#{mutation.incident_id}", "SK": "META"}
        public_update = {
            "timestamp": mutation.at,
            "state": mutation.state,
            "message": _incident_message(mutation, name),
        }
        if mutation.action == "open":
            title = (
                f"Maintenance for {name}" if mutation.kind == "maintenance" else f"Availability issue affecting {name}"
            )
            meta = {
                **meta_key,
                "entityType": "incident",
                "incidentId": mutation.incident_id,
                "kind": mutation.kind,
                "state": mutation.state,
                "impact": mutation.impact,
                "title": title,
                "startedAt": mutation.started_at,
                "resolvedAt": None,
                "affectedComponentIds": [mutation.component_id],
                "updates": [public_update],
                "GSI1PK": "INCIDENTS",
                "GSI1SK": f"{mutation.started_at}#{mutation.incident_id}",
            }
            meta_action: dict[str, Any] = {
                "Put": {
                    "TableName": self.table_name,
                    "Item": self._item(meta),
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            }
        else:
            expression = "SET #state = :state, #updates = :updates"
            values: dict[str, Any] = {
                ":state": mutation.state,
                ":updates": _bounded_timeline(mutation, name, public_update),
            }
            if mutation.action == "resolve":
                expression += ", resolvedAt = :at, expiresAt = :ttl"
                values[":at"] = mutation.at
                values[":ttl"] = expires_at
            else:
                expression += " REMOVE expiresAt"
            meta_action = {
                "Update": {
                    "TableName": self.table_name,
                    "Key": self._item(meta_key),
                    "UpdateExpression": expression,
                    "ExpressionAttributeNames": {"#state": "state", "#updates": "updates"},
                    "ExpressionAttributeValues": self._values(values),
                    "ConditionExpression": "attribute_exists(PK)",
                }
            }

        update = {
            "PK": f"INCIDENT#{mutation.incident_id}",
            "SK": f"UPDATE#{mutation.at}#{mutation.state}",
            "entityType": "incident-update",
            "timestamp": mutation.at,
            "state": mutation.state,
            "message": public_update["message"],
            "expiresAt": expires_at,
        }
        return [
            meta_action,
            {
                "Put": {
                    "TableName": self.table_name,
                    "Item": self._item(update),
                    "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
                }
            },
        ]

    def _item(self, value: dict[str, Any]) -> dict[str, Any]:
        return {key: self._serializer.serialize(item) for key, item in value.items()}

    def _values(self, value: dict[str, Any]) -> dict[str, Any]:
        return self._item(value)


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return value


def _epoch(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def _pascal(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_"))


def _component_name(component_id: str) -> str:
    from .constants import COMPONENT_BY_ID

    return COMPONENT_BY_ID[component_id].name


def _incident_message(mutation: IncidentMutation, name: str) -> str:
    if mutation.action == "resolve":
        return f"{name} operation has been confirmed."
    if mutation.state == "monitoring":
        return f"{name} has recovered and is being monitored."
    if mutation.kind == "maintenance":
        return f"Maintenance is in progress for {name}."
    return f"We are investigating an availability issue affecting {name}."


def _bounded_timeline(
    mutation: IncidentMutation,
    name: str,
    public_update: dict[str, str],
) -> list[dict[str, str]]:
    """Build a fixed-size public timeline for an active or resolved incident."""

    opened_at = mutation.opened_at or mutation.started_at
    investigating = {
        "timestamp": opened_at,
        "state": "investigating",
        "message": (
            f"Maintenance is in progress for {name}."
            if mutation.kind == "maintenance"
            else f"We are investigating an availability issue affecting {name}."
        ),
    }
    timeline = [investigating]
    if mutation.action == "update":
        timeline.append(public_update)
    elif mutation.action == "resolve":
        if mutation.monitoring_at:
            timeline.append(
                {
                    "timestamp": mutation.monitoring_at,
                    "state": "monitoring",
                    "message": f"{name} has recovered and is being monitored.",
                }
            )
        timeline.append(public_update)
    return timeline
