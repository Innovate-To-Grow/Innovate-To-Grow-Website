"""Campaign admin inlines and filters."""

from django.contrib import admin
from unfold.admin import TabularInline

from mail.models import RecipientLog
from mail.models.campaign import ALL_AUDIENCE_CHOICES


class RecipientLogInline(TabularInline):
    model = RecipientLog
    fields = (
        "email_address",
        "recipient_name",
        "status",
        "bounce_type",
        "error_message",
        "provider",
        "sent_at",
        "last_event_at",
    )
    readonly_fields = fields
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class AudienceTypeFilter(admin.SimpleListFilter):
    title = "audience type"
    parameter_name = "audience_type"

    def lookups(self, request, model_admin):
        return ALL_AUDIENCE_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(audience_type=self.value())
        return queryset
