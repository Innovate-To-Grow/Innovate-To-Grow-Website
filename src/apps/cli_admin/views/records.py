import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DataError
from rest_framework import status
from rest_framework.response import Response

from apps.core.services.db_tools.helpers import MAX_ROWS
from apps.core.services.db_tools.safe_orm import (
    ActionRequestError,
    field_output_name,
    json_safe,
    safe_model_fields,
    serialize_model_instance,
    validate_query_key,
    validate_selected_fields,
)

from ..services.audit import write_audit
from ..services.crud import cli_create, cli_delete, cli_update
from ..services.resolve import cli_get_object, resolve_cli_model
from ..throttles import CliReadThrottle, CliWriteThrottle
from .base import AdminAPIView
from .helpers import client_ip

EXPECTED_SNAPSHOT_HEADER = "HTTP_X_EXPECTED_SNAPSHOT"
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _int_param(params, name, default):
    raw = params.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ActionRequestError(f"{name} must be an integer.") from exc


def _expected_snapshot(request):
    raw = request.META.get(EXPECTED_SNAPSHOT_HEADER)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ActionRequestError("X-Expected-Snapshot must be valid JSON.") from exc


def _payload(request):
    return request.data if isinstance(request.data, dict) else {}


def _write(request, action, app_label, model_name, func):
    """Run a write, recording a failed-audit row (outside the rolled-back transaction)
    before re-raising so the failure is always captured."""
    try:
        return func()
    except Exception as exc:
        write_audit(
            actor=request.user,
            action=action,
            status="failed",
            app_label=app_label,
            model_name=model_name,
            error_message=str(exc),
            request_ip=client_ip(request),
        )
        raise


class RecordCollectionView(AdminAPIView):
    def get_throttles(self):
        self.throttle_classes = [CliWriteThrottle] if self.request.method == "POST" else [CliReadThrottle]
        return super().get_throttles()

    def get(self, request, app_label, model_name):
        model = resolve_cli_model(app_label, model_name, write=False)
        safe_names = {field_output_name(field) for field in safe_model_fields(model, write=False)}
        selected = request.query_params.getlist("field")
        selected_fields = validate_selected_fields(selected, safe_names) if selected else sorted(safe_names)

        filters = {}
        for raw in request.query_params.getlist("filter"):
            if "=" not in raw:
                raise ActionRequestError("filter must be in 'key=value' form.")
            key, value = raw.split("=", 1)
            validate_query_key(key, safe_names)
            filters[key] = value

        orderings = request.query_params.getlist("order")
        for key in orderings:
            validate_query_key(key, safe_names)

        limit = _int_param(request.query_params, "limit", MAX_ROWS)
        if limit < 1 or limit > MAX_ROWS:
            limit = MAX_ROWS
        offset = max(_int_param(request.query_params, "offset", 0), 0)

        try:
            qs = model.objects.filter(**filters)
            if orderings:
                qs = qs.order_by(*orderings)
            rows = [json_safe(row) for row in qs.values(*selected_fields)[offset : offset + limit]]
            count = qs.count()
        except (ValueError, TypeError, DjangoValidationError, DataError) as exc:
            # Field/lookup KEYS are validated above; a bad filter/order VALUE
            # (e.g. year__gt=abc) only fails at query execution — map it to 400.
            raise ActionRequestError(f"Invalid filter or ordering value: {exc}") from exc
        return Response(
            {
                "model": model._meta.label,
                "count": count,
                "offset": offset,
                "limit": limit,
                "results": rows,
            }
        )

    def post(self, request, app_label, model_name):
        obj = _write(
            request,
            "create",
            app_label,
            model_name,
            lambda: cli_create(
                actor=request.user,
                request_ip=client_ip(request),
                app_label=app_label,
                model_name=model_name,
                fields=_payload(request),
            ),
        )
        return Response(serialize_model_instance(obj, write=False), status=status.HTTP_201_CREATED)


class RecordDetailView(AdminAPIView):
    def get_throttles(self):
        self.throttle_classes = [CliReadThrottle] if self.request.method == "GET" else [CliWriteThrottle]
        return super().get_throttles()

    def get(self, request, app_label, model_name, pk):
        model = resolve_cli_model(app_label, model_name, write=False)
        obj = cli_get_object(model, pk)
        return Response(serialize_model_instance(obj, write=False))

    def patch(self, request, app_label, model_name, pk):
        obj = _write(
            request,
            "update",
            app_label,
            model_name,
            lambda: cli_update(
                actor=request.user,
                request_ip=client_ip(request),
                app_label=app_label,
                model_name=model_name,
                pk=pk,
                changes=_payload(request),
                expected_snapshot=_expected_snapshot(request),
            ),
        )
        return Response(serialize_model_instance(obj, write=False))

    def delete(self, request, app_label, model_name, pk):
        confirm = request.query_params.get("confirm_cascade", "").lower() in TRUE_VALUES
        result = _write(
            request,
            "delete",
            app_label,
            model_name,
            lambda: cli_delete(
                actor=request.user,
                request_ip=client_ip(request),
                app_label=app_label,
                model_name=model_name,
                pk=pk,
                confirm_cascade=confirm,
                expected_snapshot=_expected_snapshot(request),
            ),
        )
        return Response(result)
