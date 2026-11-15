"""Mail → SMS Opt-outs: the numbers no text goes to, the AWS sync's state and "Sync with AWS now".

AWS rows (a person replied STOP) are read-only here: AWS lists them until the person opts back in, and the sync
follows. Staff may add a number a person asked them to stop texting, and lift only such a staff opt-out. Every add,
lift and sync writes an admin history line.
"""

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from unfold.decorators import display

from apps.core.admin import BaseModelAdmin
from apps.mail.models import SmsOptOut, SmsOptOutSyncState
from apps.mail.services.sms.opt_out_sync import sync_opt_outs
from apps.mail.services.sms.opt_outs import (
    active_opt_outs,
    add_staff_opt_out,
    lift_staff_opt_out,
    matching_contact_phones,
    normalize_phone,
)


def _back_to(request) -> str:
    """The admin page the sync was started from (SMS Settings or this list), never another site."""
    target = request.POST.get("next") or ""
    if target.startswith("/admin/mail/") and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse("admin:mail_smsoptout_changelist")


class SmsOptOutAddForm(forms.ModelForm):
    class Meta:
        model = SmsOptOut
        fields = ("phone_number", "note")
        help_texts = {
            "phone_number": "The US number to stop texting, for example +12095551234 or (209) 555-1234.",
            "note": "Why: who asked, and how.",
        }

    def clean_phone_number(self):
        number = normalize_phone(self.cleaned_data.get("phone_number"))
        if not number:
            raise forms.ValidationError("Enter a US phone number, for example +12095551234.")
        if active_opt_outs().filter(phone_number=number).exists():
            raise forms.ValidationError("This number is already opted out.")
        return number

    def validate_unique(self):
        # A number that opted back in keeps its row: the add reopens it (``add_staff_opt_out``).
        return


class ActiveFilter(admin.SimpleListFilter):
    title = "status"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return (("active", "Opted out"), ("cleared", "Opted back in"))

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(cleared_at__isnull=True)
        if self.value() == "cleared":
            return queryset.filter(cleared_at__isnull=False)
        return queryset


@admin.register(SmsOptOut)
class SmsOptOutAdmin(BaseModelAdmin):
    add_form = SmsOptOutAddForm
    change_list_template = "admin/mail/smsoptout/change_list.html"
    require_confirmation = False
    list_display = (
        "phone_number",
        "status_badge",
        "source",
        "opted_out_at",
        "members",
        "contacts_unsubscribed_at",
        "last_seen_in_aws_at",
        "cleared_at",
    )
    list_filter = (ActiveFilter, "source")
    search_fields = ("phone_number", "note")
    ordering = ("-opted_out_at",)
    actions = ["lift_staff_opt_outs"]
    readonly_fields = (
        "phone_number",
        "source",
        "opted_out_at",
        "end_user_opted_out",
        "last_seen_in_aws_at",
        "contacts_unsubscribed_at",
        "cleared_at",
        "cleared_reason",
        "note",
        "created_by",
    )

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        return ("phone_number", "note") if obj is None else self.readonly_fields

    def get_readonly_fields(self, request, obj=None):
        return () if obj is None else super().get_readonly_fields(request, obj)

    def has_change_permission(self, request, obj=None):
        # Rows change only through the sync, an add, or the lift action: the detail page is read-only.
        return obj is None and self._has_app_access(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        row = add_staff_opt_out(obj.phone_number, note=obj.note, actor=request.user)
        for field in SmsOptOut._meta.concrete_fields:
            setattr(obj, field.attname, getattr(row, field.attname))
        obj._state.adding = False
        obj._state.db = row._state.db

    @display(description="Status", label={"Opted out": "danger", "Opted back in": "success"})
    def status_badge(self, obj):
        return "Opted out" if obj.is_active else "Opted back in"

    @display(description="Members")
    def members(self, obj):
        phones = matching_contact_phones([obj.phone_number]).get(obj.phone_number, [])
        labels = [str(phone.member) for phone in phones if phone.member_id]
        return ", ".join(labels) or "-"

    @admin.action(description="Lift selected staff opt-outs", permissions=["lift"])
    def lift_staff_opt_outs(self, request, queryset):
        lifted = [row for row in queryset if lift_staff_opt_out(row, actor=request.user)]
        if lifted:
            LogEntry.objects.log_actions(
                user_id=request.user.pk,
                queryset=lifted,
                action_flag=CHANGE,
                change_message=[{"changed": {"fields": ["Opted back in (staff lifted the opt-out)"]}}],
                single_object=False,
            )
        skipped = queryset.count() - len(lifted)
        message = f"Lifted {len(lifted)} staff opt-out(s)."
        if skipped:
            message += (
                f" {skipped} left as they are: an AWS opt-out ends only when the person replies START to the number "
                "(the next sync then clears it), and one already lifted stays lifted."
            )
        self.message_user(request, message, messages.SUCCESS if lifted else messages.WARNING)

    def has_lift_permission(self, request):
        return self._has_app_access(request)

    def get_urls(self):
        return [
            path("sync/", self.admin_site.admin_view(self.sync_view), name="mail_smsoptout_sync"),
            *super().get_urls(),
        ]

    def sync_view(self, request):
        """POST: read AWS's opted-out list now (read only on AWS's side) and apply it."""
        if not self._has_app_access(request):
            raise PermissionDenied
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        result = sync_opt_outs()
        LogEntry.objects.log_actions(
            user_id=request.user.pk,
            queryset=[SmsOptOutSyncState.load()],
            action_flag=CHANGE,
            change_message=f"Synced SMS opt-outs with AWS: {result.status}",
            single_object=True,
        )
        failed = result.status in (SmsOptOutSyncState.Status.FAILED, SmsOptOutSyncState.Status.NOT_CONFIGURED)
        level = messages.ERROR if failed else messages.SUCCESS
        detail = f" {result.message}" if result.message else ""
        self.message_user(
            request,
            f"AWS opt-out sync: {result.status}. Listed {result.listed}, added {result.added}, "
            f"cleared {result.cleared}.{detail}",
            level,
        )
        return HttpResponseRedirect(_back_to(request))

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "sync_state": SmsOptOutSyncState.load()}
        return super().changelist_view(request, extra_context=extra_context)
