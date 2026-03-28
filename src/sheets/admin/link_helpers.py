import json

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

ALLOWED_APP_LABELS = {"authn", "event", "news", "pages", "projects"}
SHEETLINK_FIELDSETS = (
    (None, {"fields": ("name", "account", "is_active", "sync_direction")}),
    ("Google Sheet", {"fields": ("spreadsheet_id", "sheet_name", "range_a1")}),
    ("Target Model", {"fields": ("content_type",)}),
    (
        "Column Mapping",
        {
            "fields": ("column_mapping", "fk_config"),
            "description": (
                "Map sheet headers to model fields. Use Django __ syntax for FKs: "
                '{"Year": "semester__year"}. Use "__skip__" to ignore a column.'
            ),
        },
    ),
    (
        "Upsert Configuration",
        {
            "fields": ("lookup_fields", "row_transform_hook"),
            "description": "Fields forming the unique key for upserts, and optional transform hook.",
        },
    ),
    ("Metadata", {"fields": ("id", "created_at", "updated_at"), "classes": ("collapse",)}),
)


def get_content_type_queryset():
    return ContentType.objects.filter(app_label__in=ALLOWED_APP_LABELS).order_by("app_label", "model")


def build_editor_context(obj=None):
    base_url = reverse("admin:sheets_sheetlink_model_fields", args=[0])
    return {
        "initial_mapping_json": json.dumps(obj.column_mapping if obj else {}),
        "initial_fk_config_json": json.dumps(obj.fk_config if obj else {}),
        "initial_lookup_fields_json": json.dumps(obj.lookup_fields if obj else []),
        "model_fields_url": base_url.replace("/0/", "/__CT_ID__/"),
    }


def build_model_fields(model_class):
    fields = []
    for field in model_class._meta.get_fields():
        if field.is_relation and getattr(field, "related_model", None) and field.many_to_one:
            for related_field in field.related_model._meta.get_fields():
                if not related_field.is_relation and hasattr(related_field, "column"):
                    fields.append(
                        {
                            "value": f"{field.name}__{related_field.name}",
                            "label": f"{field.name} \u2192 {related_field.name} ({related_field.get_internal_type()})",
                            "group": f"FK: {field.name}",
                        }
                    )
        elif not field.is_relation and hasattr(field, "column"):
            if field.primary_key and field.name == "id":
                continue
            fields.append(
                {
                    "value": field.name,
                    "label": f"{field.name} ({field.get_internal_type()})",
                    "group": "Direct fields",
                }
            )
    return fields


def get_model_fields_response(content_type_id):
    ct = ContentType.objects.filter(id=content_type_id, app_label__in=ALLOWED_APP_LABELS).first()
    if not ct:
        return JsonResponse({"fields": []})

    model_class = ct.model_class()
    if not model_class:
        return JsonResponse({"fields": []})

    return JsonResponse({"fields": build_model_fields(model_class)})


def render_sync_template(admin_site, request, opts, template_name, title, sheet_link, **extra_context):
    return render(
        request,
        template_name,
        {
            **admin_site.each_context(request),
            "title": title,
            "opts": opts,
            "sheet_link": sheet_link,
            **extra_context,
        },
    )


def run_bulk_sync(request, queryset, sync_fn):
    success, failed = 0, 0
    for link in queryset.filter(is_active=True):
        log = sync_fn(link, triggered_by=request.user)
        if log.status == "failed":
            failed += 1
        else:
            success += 1
    messages.success(request, f"Sync complete: {success} succeeded, {failed} failed.")


def handle_sync_view(model_admin, request, object_id, action):
    sheet_link = model_admin.get_object(request, object_id)
    if sheet_link is None:
        return model_admin._get_obj_does_not_exist_redirect(request, model_admin.opts, object_id)

    template_name = "admin/sheets/sheetlink/sync_confirm.html"
    title_prefix = "Pull from Sheet" if action == "pull" else "Push to Sheet"
    context = {"action": action}
    if request.method == "POST":
        from sheets.services.sync import pull_from_sheet, push_to_sheet

        sync_fn = pull_from_sheet if action == "pull" else push_to_sheet
        template_name = "admin/sheets/sheetlink/sync_result.html"
        title_prefix = "Pull Result" if action == "pull" else "Push Result"
        context = {"sync_log": sync_fn(sheet_link, triggered_by=request.user)}

    return render_sync_template(
        model_admin.admin_site,
        request,
        model_admin.opts,
        template_name,
        f"{title_prefix}: {sheet_link.name}",
        sheet_link,
        **context,
    )
