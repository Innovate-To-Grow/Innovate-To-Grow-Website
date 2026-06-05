from django.apps import apps
from rest_framework.response import Response

from apps.core.services.db_tools.safe_orm import is_model_denied, safe_model_fields

from ..services.resolve import is_cli_denied, resolve_cli_model
from ..services.schema import field_schema_verbose
from ..throttles import CliReadThrottle
from .base import AdminAPIView


def _is_cli_denied(model, *, write):
    return is_model_denied(model, write=write) or is_cli_denied(model)


class ModelListView(AdminAPIView):
    throttle_classes = [CliReadThrottle]

    def get(self, request):
        rows = []
        for model in apps.get_models():
            if _is_cli_denied(model, write=False):
                continue
            rows.append(
                {
                    "app_label": model._meta.app_label,
                    "model_name": model._meta.object_name,
                    "label": model._meta.label,
                    "writable": not _is_cli_denied(model, write=True),
                }
            )
        rows.sort(key=lambda row: row["label"])
        return Response(rows)


class ModelSchemaView(AdminAPIView):
    throttle_classes = [CliReadThrottle]

    def get(self, request, app_label, model_name):
        model = resolve_cli_model(app_label, model_name, write=False)
        return Response(
            {
                "model": model._meta.label,
                "primary_key": model._meta.pk.name,
                "readable_fields": [
                    field_schema_verbose(field, write=False) for field in safe_model_fields(model, write=False)
                ],
                "writable_fields": [
                    field_schema_verbose(field, write=True) for field in safe_model_fields(model, write=True)
                ],
            }
        )
