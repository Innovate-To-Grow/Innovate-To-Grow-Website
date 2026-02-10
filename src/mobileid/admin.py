"""
MobileID admin configuration.

Includes a barcode scanning interface for the Transaction model that
supports both camera-based scanning (html5-qrcode) and manual input.
"""

import json

from django.contrib import admin
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import Barcode, MobileID, Transaction


@admin.register(Barcode)
class BarcodeAdmin(admin.ModelAdmin):
    """Admin for Barcode model."""

    list_display = ("barcode", "barcode_type", "model_user", "profile_name", "created_at")
    list_filter = ("barcode_type", "created_at")
    search_fields = ("barcode", "model_user__username", "model_user__email", "profile_name")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ["model_user"]

    fieldsets = (
        (None, {"fields": ("model_user", "barcode_type", "barcode")}),
        ("Profile", {"fields": ("profile_name", "profile_img", "profile_information_id")}),
        ("Metadata", {"fields": ("id", "created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(MobileID)
class MobileIDAdmin(admin.ModelAdmin):
    """Admin for MobileID model."""

    list_display = ("model_user", "user_barcode", "created_at")
    list_filter = ("created_at",)
    search_fields = ("model_user__username", "model_user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ["model_user", "user_barcode"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """
    Admin for Transaction model with barcode scanning capability.

    Adds a "Scan Barcode" button on the change list that opens a
    scanning page supporting camera scan and manual barcode input.
    """

    list_display = ("id", "user_display", "barcode_display", "created_at")
    list_filter = ("barcode_used__barcode_type", "created_at")
    search_fields = (
        "model_user__username",
        "model_user__email",
        "barcode_used__barcode",
    )
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ["model_user", "barcode_used"]

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    @admin.display(description="User", ordering="model_user__username")
    def user_display(self, obj):
        return obj.model_user.username if obj.model_user_id else "-"

    @admin.display(description="Barcode", ordering="barcode_used__barcode")
    def barcode_display(self, obj):
        if not obj.barcode_used_id:
            return "-"
        bc = obj.barcode_used
        return format_html(
            '<span title="{}">{}</span>',
            bc.get_barcode_type_display(),
            bc.barcode,
        )

    # ------------------------------------------------------------------
    # Custom URLs
    # ------------------------------------------------------------------

    def get_urls(self):
        """Add custom URLs for the barcode scanning interface."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "scan/",
                self.admin_site.admin_view(self.scan_view),
                name="mobileid_transaction_scan",
            ),
            path(
                "scan/lookup/",
                self.admin_site.admin_view(self.scan_lookup_view),
                name="mobileid_transaction_scan_lookup",
            ),
            path(
                "scan/confirm/",
                self.admin_site.admin_view(self.scan_confirm_view),
                name="mobileid_transaction_scan_confirm",
            ),
        ]
        return custom_urls + urls

    # ------------------------------------------------------------------
    # Scanning views
    # ------------------------------------------------------------------

    def scan_view(self, request):
        """Render the barcode scanning page."""
        context = {
            **self.admin_site.each_context(request),
            "title": "Scan Barcode",
            "opts": self.model._meta,
            "lookup_url": reverse("admin:mobileid_transaction_scan_lookup"),
            "confirm_url": reverse("admin:mobileid_transaction_scan_confirm"),
            "changelist_url": reverse("admin:mobileid_transaction_changelist"),
        }
        return render(request, "admin/mobileid/transaction/scan.html", context)

    def scan_lookup_view(self, request):
        """
        AJAX endpoint: look up a barcode and return user info as JSON.

        POST body: ``{"barcode": "value"}``
        """
        if request.method != "POST":
            return JsonResponse({"error": "POST required"}, status=405)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        barcode_value = (data.get("barcode") or "").strip()
        if not barcode_value:
            return JsonResponse({"found": False, "error": "Barcode value is required."})

        barcode = (
            Barcode.objects.filter(barcode=barcode_value, is_deleted=False)
            .select_related("model_user")
            .first()
        )
        if not barcode:
            return JsonResponse({
                "found": False,
                "error": f"No barcode found for '{barcode_value}'.",
            })

        user = barcode.model_user
        return JsonResponse({
            "found": True,
            "barcode_id": str(barcode.pk),
            "barcode_value": barcode.barcode,
            "barcode_type": barcode.get_barcode_type_display(),
            "user_id": str(user.pk),
            "username": user.username,
            "full_name": user.get_full_name() if hasattr(user, "get_full_name") else "",
            "email": user.email,
            "profile_name": barcode.profile_name or "",
            "profile_img": barcode.profile_img or "",
        })

    def scan_confirm_view(self, request):
        """
        AJAX endpoint: create a Transaction record after admin confirms.

        POST body: ``{"barcode_id": "uuid", "user_id": "uuid"}``
        """
        if request.method != "POST":
            return JsonResponse({"error": "POST required"}, status=405)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        barcode_id = data.get("barcode_id")
        user_id = data.get("user_id")

        if not barcode_id or not user_id:
            return JsonResponse({
                "success": False,
                "error": "barcode_id and user_id are required.",
            })

        try:
            barcode = Barcode.objects.get(pk=barcode_id, is_deleted=False)
        except Barcode.DoesNotExist:
            return JsonResponse({"success": False, "error": "Barcode not found."})

        transaction = Transaction.objects.create(
            model_user_id=user_id,
            barcode_used=barcode,
        )
        return JsonResponse({
            "success": True,
            "transaction_id": str(transaction.pk),
            "message": f"Transaction created for {barcode.model_user.username}.",
        })

    # ------------------------------------------------------------------
    # Change list override to inject scan URL
    # ------------------------------------------------------------------

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["scan_url"] = reverse("admin:mobileid_transaction_scan")
        return super().changelist_view(request, extra_context=extra_context)
