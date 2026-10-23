from django.contrib import admin, messages
from django.utils.html import format_html

from apps.cms.services.styles.revisions import restore_custom_css
from apps.core.admin import ReadOnlyModelAdmin

from ...models import CustomCssRevision


@admin.register(CustomCssRevision)
class CustomCssRevisionAdmin(ReadOnlyModelAdmin):
    list_display = ("created_at", "created_by", "size", "first_line")
    readonly_fields = ("created_at", "created_by", "css_display")
    fields = ("created_at", "created_by", "css_display")
    actions = ["restore_revision"]

    @admin.display(description="Size")
    def size(self, obj):
        return f"{len(obj.css.encode('utf-8'))} bytes"

    @admin.display(description="Starts with")
    def first_line(self, obj):
        line = next((text.strip() for text in obj.css.splitlines() if text.strip()), "(empty)")
        return line[:80]

    @admin.display(description="CSS")
    def css_display(self, obj):
        return format_html('<pre class="font-mono text-sm whitespace-pre-wrap">{}</pre>', obj.css or "(empty)")

    @admin.action(description="Restore the selected revision as the live custom CSS")
    def restore_revision(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one revision to restore.", messages.ERROR)
            return
        revision = queryset.get()
        restore_custom_css(revision, request.user)
        self.message_user(request, f"Restored the custom CSS saved {revision.created_at:%Y-%m-%d %H:%M}.")
