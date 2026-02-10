from django.contrib import admin
from django.utils.html import escape, format_html

from ..models import EmailLayout, EmailMessageContext, EmailMessageLayout
from ..providers.email import render_email_layout
from .utils import _collect_highlight_values, _highlight_values, _inject_preview_style


class EmailMessageContextInline(admin.TabularInline):
    model = EmailMessageContext
    extra = 0
    fields = (
        "name",
        "is_default",
        "context_data",
        "description",
        "created_at",
        "updated_at",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(EmailMessageLayout)
class EmailMessageLayoutAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "is_active", "updated_at")
    list_filter = ("is_active", "created_at", "updated_at")
    search_fields = ("key", "name", "subject_template", "body_template", "description")
    ordering = ("name",)
    inlines = [EmailMessageContextInline]
    readonly_fields = ("preview_subject", "preview_html", "created_at", "updated_at")
    fieldsets = (
        (
            "Template",
            {
                    "fields": (
                        "layout",
                        "key",
                        "name",
                        "is_active",
                        "description",
                        "subject_template",
                        "preheader_template",
                        "body_template",
                        "default_context",
                ),
            },
        ),
        (
            "Preview",
            {
                "fields": ("preview_subject", "preview_html"),
                "description": "Preview uses default_context or the first preview context.",
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Preview Subject")
    def preview_subject(self, obj):
        if not obj:
            return "Save to preview"
        context = self._build_preview_context(obj)
        subject, _, _, _ = obj.render(context=context)
        return subject or "—"

    @admin.display(description="Preview HTML")
    def preview_html(self, obj):
        if not obj:
            return "Save to preview"
        context = self._build_preview_context(obj)
        subject, body, preheader, ctx = obj.render(context=context)
        if preheader:
            ctx = {**ctx, "preheader": preheader}
        html_body, _ = render_email_layout(
            subject=subject or obj.subject_template,
            body=body,
            context=ctx,
            layout=obj.layout,
        )
        highlight_values = _collect_highlight_values(ctx, subject=subject)
        html_body = _inject_preview_style(_highlight_values(html_body, highlight_values))
        return format_html(
            '<iframe style="width:100%; height:600px; border:1px solid #d0d4d8; border-radius:8px;" srcdoc="{}"></iframe>',
            escape(html_body),
        )

    def _build_preview_context(self, obj):
        context = obj.get_preview_context()
        context.setdefault("recipient_name", "Sample User")
        context.setdefault("user_name", context["recipient_name"])
        context.setdefault("recipient_email", "preview@example.com")
        return context


@admin.register(EmailMessageContext)
class EmailMessageContextAdmin(admin.ModelAdmin):
    list_display = ("layout", "name", "is_default", "updated_at")
    list_filter = ("is_default", "created_at", "updated_at")
    search_fields = ("layout__name", "layout__key", "name", "description")
    ordering = ("layout__name", "name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(EmailLayout)
class EmailLayoutAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "is_active", "is_default", "updated_at")
    list_filter = ("is_active", "is_default", "created_at", "updated_at")
    search_fields = ("key", "name", "description", "html_template")
    ordering = ("name",)
    readonly_fields = ("preview_html", "created_at", "updated_at")
    fieldsets = (
        (
            "Layout",
            {
                "fields": (
                    "key",
                    "name",
                    "is_active",
                    "is_default",
                    "description",
                    "html_template",
                ),
            },
        ),
        (
            "Preview",
            {
                "fields": ("preview_html",),
                "description": "Preview uses sample content and brand settings.",
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Preview HTML")
    def preview_html(self, obj):
        if not obj:
            return "Save to preview"
        context = {
            "recipient_name": "Sample User",
            "recipient_email": "preview@example.com",
        }
        html_body, _ = render_email_layout(
            subject="Sample Email Subject",
            body="<p>This is a preview of the email body content.</p>",
            context=context,
            layout=obj,
        )
        highlight_values = _collect_highlight_values(context, subject="Sample Email Subject")
        html_body = _inject_preview_style(_highlight_values(html_body, highlight_values))
        return format_html(
            '<iframe style="width:100%; height:600px; border:1px solid #d0d4d8; border-radius:8px;" srcdoc="{}"></iframe>',
            escape(html_body),
        )
