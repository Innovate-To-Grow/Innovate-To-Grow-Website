"""Mail → SMS Settings: the one ``SmsConfig`` row, the opt-out sync's state, and the short /register link's QR code.

Turning personal sign-in links (or links in SMS) off revokes the personal links already texted, for good
(``SmsConfig.save``). Staff see that before saving: the "Links in SMS" section says how many still work, the
type-to-confirm page lists the revocation with the field changes, and the save reports how many were revoked. Each
revocation is kept in SMS link revocations (who, when, how many), the last few shown on this page.
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from unfold.widgets import UnfoldAdminSelectWidget

from apps.core.admin import BaseModelAdmin
from apps.mail.models import SmsConfig, SmsLinkRevocation, SmsLinkToken, SmsOptOutSyncState
from apps.mail.models.sms_config import DEFAULT_REGISTER_PATH
from apps.mail.redirects import get_login_redirect_choices
from apps.mail.services.sms.quiet_hours import held_until
from apps.mail.services.sms.register_link import register_qr, register_url

SIGN_IN_CHOICE = (DEFAULT_REGISTER_PATH, f"Sign-in page: email or phone sign-up ({DEFAULT_REGISTER_PATH})")
LINKS_FIELDSET = "Links in SMS"
LINKS_WARNING = (
    "Open item before turning links on: confirm that the sending number's 10DLC campaign (or toll-free verification) "
    "declares embedded links, with sample messages on this site's domain. If it doesn't, the registration must be "
    "updated first (approval can take days to weeks). No public link shorteners are used: every link is on this site."
)
REVOCATION_WARNING = (
    "Turning personal sign-in links or links in SMS off revokes every personal sign-in link already texted, for good: "
    "turning them on again does not bring any back, and whoever opens one gets the sign-in page. Shared links are not "
    "affected. Personal sign-in links that still work now: {live}."
)
REVOKED_FOR_GOOD = "Revoked for good: turning them on again does not bring them back"


def live_personal_links(request) -> int:
    """Personal sign-in links that could still sign someone in (counted once per request)."""
    if not hasattr(request, "_sms_live_personal_links"):
        request._sms_live_personal_links = SmsLinkToken.objects.outstanding_personal().count()
    return request._sms_live_personal_links


def revocation_message(revocation: SmsLinkRevocation) -> str:
    count = revocation.revoked_count
    if revocation.reason == SmsLinkRevocation.Reason.FOUND_OFF:
        return (
            f"Revoked {count} personal sign-in link(s) that still worked although personal sign-in links were off "
            "(they had been turned off outside the admin)."
        )
    return (
        f"Personal sign-in links are off: {count} link(s) already texted were revoked for good. Turning them on "
        "again won't bring them back; whoever opens one gets the sign-in page."
    )


class SmsConfigForm(forms.ModelForm):
    register_redirect_path = forms.ChoiceField(
        choices=(),
        label="/register leads to",
        help_text=SmsConfig._meta.get_field("register_redirect_path").help_text,
        widget=UnfoldAdminSelectWidget,
    )

    class Meta:
        model = SmsConfig
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.initial.get("register_redirect_path") or getattr(self.instance, "register_redirect_path", "")
        choices = [SIGN_IN_CHOICE, *get_login_redirect_choices(current_path=current)]
        self.fields["register_redirect_path"].choices = list(dict(choices).items())


@admin.register(SmsConfig)
class SmsConfigAdmin(BaseModelAdmin):
    form = SmsConfigForm
    change_form_template = "admin/mail/smsconfig/change_form.html"
    fieldsets = (
        ("Opt-out footer", {"fields": ("footer_enabled", "footer_text")}),
        (
            "Quiet hours",
            {"fields": ("quiet_hours_enabled", "quiet_hours_start", "quiet_hours_end", "quiet_hours_timezone")},
        ),
        ("Cost estimate", {"fields": ("cost_per_segment",)}),
        (LINKS_FIELDSET, {"fields": ("links_enabled", "personal_links_enabled"), "description": LINKS_WARNING}),
        ("Ticket texts", {"fields": ("ticket_sms_enabled", "ticket_sms_template", "ticket_link_validity_days")}),
        ("AWS opt-out sync", {"fields": ("opt_out_sync_enabled", "opt_out_list_name")}),
        ("Short /register link", {"fields": ("register_redirect_path",)}),
    )

    def get_fieldsets(self, request, obj=None):
        # The switches warn what turning them off does, with the number of personal links it would revoke now.
        warning = f"{LINKS_WARNING} {REVOCATION_WARNING.format(live=live_personal_links(request))}"
        return [
            (name, {**options, "description": warning}) if name == LINKS_FIELDSET else (name, options)
            for name, options in super().get_fieldsets(request, obj)
        ]

    def get_confirmation_diff(self, request, obj, form, formsets, action_type):
        # The type-to-confirm page lists the revocation a change that turns personal sign-in links off brings.
        diff = super().get_confirmation_diff(request, obj, form, formsets, action_type)
        if action_type == "change" and SmsConfig.load().personal_sign_in_on and not form.instance.personal_sign_in_on:
            diff.append(
                {
                    "field": "personal_links_revoked",
                    "label": "Personal sign-in links already texted",
                    "old_value": f"{live_personal_links(request)} still work",
                    "new_value": REVOKED_FOR_GOOD,
                }
            )
        return diff

    def save_model(self, request, obj, form, change):
        # The save revokes personal sign-in links in its own transaction when it turns them off; the audit names who.
        obj.save(actor=request.user, via=SmsLinkRevocation.Via.ADMIN)
        if obj.revocation is not None:
            self.message_user(request, revocation_message(obj.revocation), messages.WARNING)

    def get_readonly_fields(self, request, obj=None):
        # One-tap sign-in links widen what a phone number can reach: only the I2G Master turns them on or off.
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            readonly.append("personal_links_enabled")
        return readonly

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        return HttpResponseRedirect(reverse("admin:mail_smsconfig_change", args=[SmsConfig.load().pk]))

    def get_urls(self):
        return [
            path(
                "register-qr.<str:kind>",
                self.admin_site.admin_view(self.register_qr_view),
                name="mail_smsconfig_register_qr",
            ),
            *super().get_urls(),
        ]

    def register_qr_view(self, request, kind):
        """The /register QR code (``svg`` or ``png``): shown on the settings page, or downloaded (``?download=1``)
        for flyers and slides."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        try:
            body = register_qr(kind)
        except ValueError as exc:
            raise Http404("No QR code: FRONTEND_URL is not set, or the kind is not svg or png.") from exc
        response = HttpResponse(body, content_type="image/svg+xml" if kind == "svg" else "image/png")
        disposition = "attachment" if request.GET.get("download") else "inline"
        response["Content-Disposition"] = f'{disposition}; filename="i2g-register-qr.{kind}"'
        return response

    def render_change_form(self, request, context, *args, **kwargs):
        context.update(
            sync_state=SmsOptOutSyncState.load(),
            register_url=register_url(),
            quiet_until=held_until(),
            revocations=list(SmsLinkRevocation.objects.all()[:5]),
        )
        return super().render_change_form(request, context, *args, **kwargs)
