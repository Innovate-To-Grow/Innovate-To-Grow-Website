from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse

from ....services.members.admins import DEACTIVATE, admin_removal_refusal
from .lockout import admins_in


def get_primary_email_display(member):
    return member.get_primary_email() or "-"


def get_primary_phone_display(member):
    phone = member.get_primary_contact_phone()
    if phone is None:
        return "-"
    # An unverified number cannot be used to sign in: say so where staff see the member list.
    return phone.to_e164() if phone.verified else f"{phone.to_e164()} (unverified)"


def get_full_name_display(member):
    return member.get_full_name() or "-"


def normalize_inline_uuid_none_values(request):
    if request.method != "POST":
        return

    inline_prefixes = ("contact_emails-", "contact_phones-")
    uuid_suffixes = ("-id", "-member")
    post_data = request.POST
    original_mutable = getattr(post_data, "_mutable", None)
    if original_mutable is not None:
        post_data._mutable = True
    try:
        for key, values in list(post_data.lists()):
            if not key.startswith(inline_prefixes) or not key.endswith(uuid_suffixes):
                continue
            normalized_values = ["" if value == "None" else value for value in values]
            if normalized_values != values:
                post_data.setlist(key, normalized_values)
    finally:
        if original_mutable is not None:
            post_data._mutable = original_mutable


def activate_members(admin_obj, request, queryset):
    with transaction.atomic():
        # Reactivating never brings back Admin: only an older release leaves an inactive account with it.
        queryset.filter(is_active=False, is_staff=True).update(is_staff=False, is_superuser=False)
        updated = queryset.update(is_active=True, registration_pending=False)
    admin_obj.message_user(request, f"{updated} member(s) activated.")


def deactivate_members(admin_obj, request, queryset):
    with transaction.atomic():
        # The whole selection or nothing: never your own Admin account, never the last active Admin.
        refusal = admin_removal_refusal(request.user, admins_in(queryset), action=DEACTIVATE)
        if refusal:
            admin_obj.message_user(request, f"{refusal} No member was deactivated.", level=messages.ERROR)
            return
        # An explicit admin deactivation also ends any unfinished self-service signup, so the
        # email-code flow can't activate the account afterwards, and removes Admin access (as Member.save() does):
        # a deactivated account is never an Admin.
        updated = queryset.update(is_active=False, registration_pending=False, is_staff=False, is_superuser=False)
    admin_obj.message_user(request, f"{updated} member(s) deactivated.")


def build_excel_response(content, filename):
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_members_response(queryset):
    from django.utils import timezone

    from ....services.members.export.excel import export_members_to_excel

    content = export_members_to_excel(queryset)
    filename = f"members_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return build_excel_response(content, filename)


def build_vcard_response(content, filename):
    response = HttpResponse(content, content_type="text/vcard; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_members_vcard_response(queryset):
    from django.utils import timezone

    from ....services.members.export.vcard import export_members_to_vcard

    content = export_members_to_vcard(queryset)
    filename = f"members_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.vcf"
    return build_vcard_response(content, filename)


def download_template_view(admin_obj, request):
    from ....services.members.import_ import generate_template_excel

    try:
        content = generate_template_excel()
        return build_excel_response(content, "member_import_template.xlsx")
    except ImportError as exc:
        admin_obj.message_user(request, str(exc), level="error")
        return HttpResponseRedirect(reverse("admin:authn_member_changelist"))


def export_excel_view(admin_obj, request):
    return export_members_response(admin_obj.get_queryset(request))
