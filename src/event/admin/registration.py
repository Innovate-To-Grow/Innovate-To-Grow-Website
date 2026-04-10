import logging

from django import forms
from django.contrib import admin, messages
from django.http import JsonResponse
from django.urls import path

from core.admin import BaseModelAdmin

from ..models import Event, EventRegistration, Ticket

logger = logging.getLogger(__name__)

_VIEW_READONLY_FIELDS = (
    "member",
    "event",
    "ticket",
    "ticket_code",
    "attendee_first_name",
    "attendee_last_name",
    "attendee_email",
    "attendee_secondary_email",
    "attendee_phone",
    "phone_verified",
    "attendee_organization",
    "question_answers",
    "ticket_email_sent_at",
    "ticket_email_error",
    "created_at",
    "updated_at",
)

_ADD_READONLY_FIELDS = (
    "ticket_code",
    "ticket_email_sent_at",
    "ticket_email_error",
    "created_at",
    "updated_at",
)

_VIEW_FIELDSETS = (
    (
        "Attendee",
        {
            "fields": (
                "attendee_first_name",
                "attendee_last_name",
                "attendee_email",
                "attendee_secondary_email",
                "attendee_phone",
                "phone_verified",
                "attendee_organization",
            ),
        },
    ),
    (
        "Ticket",
        {
            "fields": ("event", "ticket", "ticket_code", "member"),
        },
    ),
    (
        "Questions & Answers",
        {
            "classes": ("collapse",),
            "fields": ("question_answers",),
        },
    ),
    (
        "Email Status",
        {
            "classes": ("collapse",),
            "fields": ("ticket_email_sent_at", "ticket_email_error"),
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

_ADD_FIELDSETS = (
    (
        "Registration",
        {
            "fields": ("member", "event", "ticket"),
        },
    ),
    (
        "Attendee overrides",
        {
            "description": "Leave blank to auto-fill from the member's profile.",
            "classes": ("collapse",),
            "fields": (
                "attendee_first_name",
                "attendee_last_name",
                "attendee_email",
                "attendee_secondary_email",
                "attendee_phone",
                "attendee_organization",
            ),
        },
    ),
    (
        "Options",
        {
            "fields": ("send_ticket_email",),
        },
    ),
)


class EventRegistrationAdminForm(forms.ModelForm):
    send_ticket_email = forms.BooleanField(
        required=False,
        initial=False,
        label="Send ticket email to attendee",
        help_text="If checked, a confirmation email with the ticket barcode will be sent after saving.",
    )

    class Meta:
        model = EventRegistration
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        event = cleaned.get("event")
        ticket = cleaned.get("ticket")
        member = cleaned.get("member")

        if event and ticket and ticket.event_id != event.pk:
            raise forms.ValidationError({"ticket": "This ticket does not belong to the selected event."})

        if member and event and not self.instance.pk:
            duplicate = EventRegistration.objects.filter(member=member, event=event).exists()
            if duplicate:
                raise forms.ValidationError(
                    {"member": "This member is already registered for the selected event."}
                )

        return cleaned

    def clean_attendee_phone(self):
        phone = self.cleaned_data.get("attendee_phone", "").strip()
        if not phone:
            return phone
        from event.views.registration import _validate_phone_digits

        error = _validate_phone_digits(phone, "0-GENERIC")
        if error:
            raise forms.ValidationError(error)
        return phone


@admin.register(EventRegistration)
class EventRegistrationAdmin(BaseModelAdmin):
    form = EventRegistrationAdminForm

    class Media:
        js = ("event/js/registration_detail_panels.js",)

    list_display = (
        "ticket_code",
        "attendee_first_name",
        "attendee_last_name",
        "attendee_email",
        "attendee_secondary_email",
        "attendee_phone",
        "phone_verified",
        "ticket",
        "event",
        "created_at",
    )
    list_filter = ("event", "ticket")
    search_fields = (
        "attendee_first_name",
        "attendee_last_name",
        "attendee_email",
        "attendee_secondary_email",
        "attendee_phone",
        "attendee_organization",
        "ticket_code",
    )
    autocomplete_fields = ["member"]
    ordering = ("-created_at",)
    actions = ["resend_ticket_email"]

    @admin.action(description="Resend ticket email")
    def resend_ticket_email(self, request, queryset):
        from event.services.ticket_mail import send_ticket_email

        sent = 0
        for registration in queryset.select_related("event", "ticket", "member"):
            try:
                send_ticket_email(registration)
                sent += 1
            except Exception:
                logger.exception("Failed to send ticket email for registration %s", registration.pk)
                messages.error(
                    request,
                    f"Failed to send email for {registration.attendee_name or registration.ticket_code}.",
                )
        if sent:
            messages.success(request, f"Sent ticket email to {sent} registration(s).")

    def get_urls(self):
        custom = [
            path("member-info/<uuid:pk>/", self.admin_site.admin_view(self._member_info_view), name="reg-member-info"),
            path("event-info/<uuid:pk>/", self.admin_site.admin_view(self._event_info_view), name="reg-event-info"),
        ]
        return custom + super().get_urls()

    # noinspection PyMethodMayBeStatic
    def _member_info_view(self, request, pk):
        from authn.models import Member

        try:
            member = Member.objects.get(pk=pk)
        except Member.DoesNotExist:
            return JsonResponse({"error": "Not found"}, status=404)

        emails = list(
            member.contact_emails.order_by("email_type", "created_at").values_list("email_address", flat=True)
        )
        phones = list(
            member.contact_phones.order_by("-verified", "created_at").values_list("phone_number", flat=True)
        )
        return JsonResponse({
            "name": member.get_full_name(),
            "emails": emails,
            "phones": phones,
            "organization": member.organization or "",
            "title": member.title or "",
        })

    # noinspection PyMethodMayBeStatic
    def _event_info_view(self, request, pk):
        try:
            event = Event.objects.prefetch_related("tickets", "questions").get(pk=pk)
        except Event.DoesNotExist:
            return JsonResponse({"error": "Not found"}, status=404)

        from django.db.models import Count

        ticket_data = (
            event.tickets.annotate(reg_count=Count("registrations"))
            .order_by("order", "name")
            .values("name", "reg_count")
        )
        tickets = [{"name": t["name"], "registrations": t["reg_count"]} for t in ticket_data]
        total_registrations = sum(t["reg_count"] for t in ticket_data)

        questions = [
            {"text": q.text, "required": q.is_required}
            for q in event.questions.order_by("order")
        ]

        return JsonResponse({
            "name": event.name,
            "slug": event.slug,
            "date": event.date.isoformat(),
            "location": event.location,
            "description": event.description,
            "is_live": event.is_live,
            "allow_secondary_email": event.allow_secondary_email,
            "collect_phone": event.collect_phone,
            "verify_phone": event.verify_phone,
            "total_registrations": total_registrations,
            "tickets": tickets,
            "questions": questions,
        })

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return _ADD_READONLY_FIELDS
        return _VIEW_READONLY_FIELDS

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return _ADD_FIELDSETS
        return _VIEW_FIELDSETS

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "ticket":
            event_id = request.POST.get("event") or request.GET.get("event")
            if event_id:
                kwargs["queryset"] = Ticket.objects.filter(event_id=event_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        try:
            from event.services.registration_sheet_sync import schedule_registration_sync

            schedule_registration_sync(obj.event)
        except Exception:
            logger.exception("Sheet sync failed for registration %s", obj.pk)

        if form.cleaned_data.get("send_ticket_email"):
            try:
                from event.services.ticket_mail import send_ticket_email

                send_ticket_email(obj)
            except Exception:
                logger.exception("Failed to send ticket email for registration %s", obj.pk)

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_add_permission(self, request):
        return True

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_change_permission(self, request, obj=None):
        return False

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        return True
