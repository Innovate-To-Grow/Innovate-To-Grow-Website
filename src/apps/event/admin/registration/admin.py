from functools import partial

from django.contrib import admin
from django.db import transaction
from django.shortcuts import redirect
from django.urls import path, reverse
from unfold.decorators import display

from apps.core.admin import BaseModelAdmin
from apps.core.utils.access import user_can_access_app

from ...models import Event, EventRegistration, Ticket
from .changelist import SemesterListFilter, build_toolbar, clear_filters_url
from .config import (
    ADD_FIELDSETS,
    ADD_READONLY_FIELDS,
    CHANGE_FIELDSETS,
    CHANGE_READONLY_FIELDS,
)
from .exports import RegistrationExportMixin
from .forms import EventRegistrationAdminForm
from .info_views import RegistrationInfoViewsMixin
from .ticket_emails import TicketEmailAdminMixin


@admin.register(EventRegistration)
class EventRegistrationAdmin(
    RegistrationExportMixin,
    TicketEmailAdminMixin,
    RegistrationInfoViewsMixin,
    BaseModelAdmin,
):
    form = EventRegistrationAdminForm
    change_list_template = "admin/event/eventregistration/change_list.html"
    export_filename = "event_registrations"

    class Media:
        css = {"all": ("event/css/event_admin/registration_changelist.css",)}
        js = (
            "event/js/event_admin/registration_detail_panels.js",
            "event/js/event_admin/registration_changelist_toolbar.js",
        )

    # Five columns so the list fits a 1024px window without scrolling sideways: the attendee's secondary email,
    # phone and verification flags are on the change form, in the export, and searchable.
    list_display = ("ticket_code", "attendee", "event", "ticket", "created_at")
    list_filter = (SemesterListFilter, "event", "ticket")
    search_fields = (
        "attendee_first_name",
        "attendee_last_name",
        "attendee_email",
        "attendee_secondary_email",
        "attendee_phone",
        "attendee_organization",
        "ticket_code",
        "event__name",
    )
    search_help_text = "Search name, email, phone, organization, ticket code or event"
    autocomplete_fields = ["member"]
    ordering = ("-created_at",)
    actions = ["resend_ticket_email", "revoke_login_links_action"]

    @display(description="Attendee", ordering="attendee_last_name", header=True)
    def attendee(self, obj):
        return [obj.attendee_name or "-", obj.attendee_email]

    @admin.action(description="Revoke login links (invalidate ticket email and ticket text sign-in links)")
    def revoke_login_links_action(self, request, queryset):
        from django.contrib import messages
        from django.utils import timezone

        from apps.mail.models import LoginLinkToken, SmsLinkToken
        from apps.mail.services.tokens.login_links import revoke_login_links

        revoked = revoke_login_links(LoginLinkToken.objects.filter(registration__in=queryset))
        now = timezone.now()
        revoked += SmsLinkToken.objects.filter(registration__in=queryset, expires_at__gt=now).update(
            expires_at=now, revoked_at=now, updated_at=now
        )
        self.message_user(request, f"Revoked {revoked} login link(s).", messages.SUCCESS)

    def get_urls(self):
        custom = [
            path(
                "send-all-ticket-emails/",
                self.admin_site.admin_view(self.send_all_ticket_emails_view),
                name="event_eventregistration_send_all_ticket_emails",
            ),
            path(
                "member-info/<uuid:pk>/",
                self.admin_site.admin_view(self._member_info_view),
                name="reg-member-info",
            ),
            path(
                "event-info/<uuid:pk>/",
                self.admin_site.admin_view(self._event_info_view),
                name="reg-event-info",
            ),
        ]
        return custom + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        events = list(Event.objects.order_by("-date", "name").only("pk", "name", "date"))
        extra_context = {
            **(extra_context or {}),
            "send_all_ticket_emails_url": reverse("admin:event_eventregistration_send_all_ticket_emails"),
            "sheet_sync_events": [
                {"name": event.name, "url": reverse("admin:event_event_sheet_sync", args=[event.pk])}
                for event in events
            ],
            "registration_toolbar": build_toolbar(request, events),
        }
        response = super().changelist_view(request, extra_context)
        # The Clear link needs the ChangeList, which only exists once Django has built the response.
        context = getattr(response, "context_data", None) or {}
        if "cl" in context:
            toolbar, cl = context["registration_toolbar"], context["cl"]
            toolbar["clear_url"] = clear_filters_url(cl)
            # A list filter set outside the toolbar (e.g. the ticket filter) still needs the Clear link.
            toolbar["is_filtered"] = toolbar["is_filtered"] or cl.has_active_filters
        return response

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ADD_READONLY_FIELDS
        return CHANGE_READONLY_FIELDS

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return ADD_FIELDSETS
        return CHANGE_FIELDSETS

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "ticket":
            event_id = request.POST.get("event") or request.GET.get("event")
            if event_id:
                kwargs["queryset"] = Ticket.objects.filter(event_id=event_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        if form.cleaned_data.get("send_ticket_email") or "_send_ticket_email" in request.POST:
            # The admin saves inside a transaction; the email (paced, and possibly waiting for its slot) goes after
            # the commit, so no lock is held across the provider call. Its message still reaches the response.
            transaction.on_commit(partial(self._send_ticket_email_registration, request, obj), robust=True)

    def response_change(self, request, obj):
        if "_send_ticket_email" in request.POST:
            return redirect("admin:event_eventregistration_change", obj.pk)
        return super().response_change(request, obj)

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_add_permission(self, request):
        return user_can_access_app(request.user, "event")

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj)

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        return user_can_access_app(request.user, "event")
