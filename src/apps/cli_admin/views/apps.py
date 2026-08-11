from collections import Counter

from django.apps import apps
from rest_framework.response import Response

from apps.core.utils.access import user_can_access_app

from ..auth.throttles import CliReadThrottle
from .base import AdminAPIView
from .models import _is_cli_denied


class AppListView(AdminAPIView):
    throttle_classes = [CliReadThrottle]

    def get(self, request):
        counts = Counter(
            model._meta.app_label
            for model in apps.get_models()
            if not _is_cli_denied(model, write=False) and user_can_access_app(request.user, model._meta.app_label)
        )
        rows = [{"app_label": app_label, "model_count": count} for app_label, count in counts.items()]
        rows.sort(key=lambda row: row["app_label"])
        return Response(rows)
