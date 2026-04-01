from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from ...models import MemberProfile


@admin.register(MemberProfile)
class MemberProfileAdmin(UnfoldModelAdmin):
    """Admin for MemberProfile model."""

    list_display = ("model_user", "has_profile_image_display", "updated_at")
    list_filter = ("updated_at",)
    search_fields = ("model_user__first_name", "model_user__last_name", "model_user__contact_emails__email_address")
    readonly_fields = ("updated_at",)
    autocomplete_fields = ["model_user"]

    fieldsets = (
        (None, {"fields": ("model_user",)}),
        (_("Profile Information"), {"fields": ("profile_image",)}),
        (_("Timestamps"), {"fields": ("updated_at",), "classes": ("collapse",)}),
    )

    @admin.display(description="Has Image", boolean=True)
    def has_profile_image_display(self, obj):
        return obj.has_profile_image()
