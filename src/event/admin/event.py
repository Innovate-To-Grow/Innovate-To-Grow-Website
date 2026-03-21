from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from ..models import Event, Question, Ticket


class TicketInline(TabularInline):
    model = Ticket
    extra = 0
    fields = ("name", "order")


class QuestionInline(TabularInline):
    model = Question
    extra = 0
    fields = ("text", "is_required", "order")


@admin.register(Event)
class EventAdmin(ModelAdmin):
    list_display = ("name", "date", "location", "is_live")
    list_filter = ("is_live", "date")
    search_fields = ("name", "location")
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TicketInline, QuestionInline]

    fieldsets = (
        (
            "Event Details",
            {
                "fields": ("name", "slug", "date", "location", "description", "is_live"),
            },
        ),
        (
            "System",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )
