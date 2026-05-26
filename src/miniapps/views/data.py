from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from miniapps.models import MiniApp, MiniAppDataRecord
from miniapps.serializers import MiniAppDataRecordSerializer
from miniapps.services.validation import validate_record_data


class MiniAppDataPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class MiniAppDataListCreateView(APIView):
    """List and create data records for a mini-app."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request, app_slug):
        from django.db.models.expressions import RawSQL

        app = get_object_or_404(MiniApp, slug=app_slug, status="published")
        records = app.records.all()

        ordering = request.query_params.get("ordering", "-created_at")
        base_field = ordering.lstrip("-")
        if base_field in ("created_at", "updated_at"):
            records = records.order_by(ordering)
        elif base_field in self._get_sortable_fields(app):
            desc = ordering.startswith("-")
            records = records.annotate(_sort_val=RawSQL("json_extract(data, %s)", (f"$.{base_field}",))).order_by(
                "-_sort_val" if desc else "_sort_val"
            )
        else:
            records = records.order_by("-created_at")

        paginator = MiniAppDataPagination()
        page = paginator.paginate_queryset(records, request)
        serializer = MiniAppDataRecordSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @staticmethod
    def _get_sortable_fields(app):
        schema = getattr(app, "data_schema", None)
        if not schema or not schema.fields:
            return set()
        return {
            f["name"]
            for f in schema.fields
            if f.get("type") in ("datetime", "date", "text", "integer", "float") and "__" not in f["name"]
        }

    def post(self, request, app_slug):
        app = get_object_or_404(MiniApp, slug=app_slug, status="published")

        schema = getattr(app, "data_schema", None)
        validated_data = validate_record_data(schema, request.data.get("data", {}))

        record = MiniAppDataRecord.objects.create(
            app=app,
            data=validated_data,
            created_by=request.user,
        )
        serializer = MiniAppDataRecordSerializer(record)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MiniAppDataDetailView(APIView):
    """Retrieve, update, or delete a single data record."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request, app_slug, record_id):
        app = get_object_or_404(MiniApp, slug=app_slug, status="published")
        record = get_object_or_404(MiniAppDataRecord, pk=record_id, app=app)
        serializer = MiniAppDataRecordSerializer(record)
        return Response(serializer.data)

    def patch(self, request, app_slug, record_id):
        app = get_object_or_404(MiniApp, slug=app_slug, status="published")
        record = get_object_or_404(MiniAppDataRecord, pk=record_id, app=app)

        schema = getattr(app, "data_schema", None)
        new_data = {**record.data, **request.data.get("data", {})}
        validated_data = validate_record_data(schema, new_data)

        record.data = validated_data
        record.save()
        serializer = MiniAppDataRecordSerializer(record)
        return Response(serializer.data)

    def delete(self, request, app_slug, record_id):
        app = get_object_or_404(MiniApp, slug=app_slug, status="published")
        record = get_object_or_404(MiniAppDataRecord, pk=record_id, app=app)
        record.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
