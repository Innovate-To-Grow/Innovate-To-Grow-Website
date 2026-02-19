"""
MobileID model admin configuration.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from ..models import MobileID


@admin.register(MobileID)
class MobileIDAdmin(ModelAdmin):
    """Admin for MobileID model."""

    list_display = ("model_user", "user_barcode", "created_at")
    list_filter = ("created_at",)
    search_fields = ("model_user__username", "model_user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ["model_user", "user_barcode"]
