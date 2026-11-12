from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse


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


def _drop_protected_members(admin_obj, request, queryset):
    """Exclude members the requester may not manage, and report how many were skipped.

    ``is_active`` is not in ``superuser_only_fields``, so without this a non-superuser staffer could
    deactivate the I2G Master and lock them out of the admin entirely.
    """
    protected = [member.pk for member in queryset if not admin_obj.can_manage_target(request, member)]
    if not protected:
        return queryset, 0
    return queryset.exclude(pk__in=protected), len(protected)


def activate_members(admin_obj, request, queryset):
    allowed, skipped = _drop_protected_members(admin_obj, request, queryset)
    updated = allowed.update(is_active=True, registration_pending=False)
    admin_obj.message_user(request, f"{updated} member(s) activated.")
    if skipped:
        admin_obj.message_user(
            request,
            f"{skipped} privileged account(s) skipped — only an I2G Master may change those.",
            level="warning",
        )


def deactivate_members(admin_obj, request, queryset):
    allowed, skipped = _drop_protected_members(admin_obj, request, queryset)
    # An explicit admin deactivation also ends any unfinished self-service signup, so the
    # email-code flow can't activate the account afterwards.
    updated = allowed.update(is_active=False, registration_pending=False)
    admin_obj.message_user(request, f"{updated} member(s) deactivated.")
    if skipped:
        admin_obj.message_user(
            request,
            f"{skipped} privileged account(s) skipped — only an I2G Master may change those.",
            level="warning",
        )


def build_excel_response(content, filename):
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_members_response(queryset):
    from django.utils import timezone

    from ...services.members.export_excel import export_members_to_excel

    content = export_members_to_excel(queryset)
    filename = f"members_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return build_excel_response(content, filename)


def build_vcard_response(content, filename):
    response = HttpResponse(content, content_type="text/vcard; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_members_vcard_response(queryset):
    from django.utils import timezone

    from ...services.members.export_vcf import export_members_to_vcard

    content = export_members_to_vcard(queryset)
    filename = f"members_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.vcf"
    return build_vcard_response(content, filename)


def download_template_view(admin_obj, request):
    from ...services.members.import_ import generate_template_excel

    if not admin_obj.has_view_permission(request):
        raise PermissionDenied("You do not have permission to access member tooling.")

    try:
        content = generate_template_excel()
        return build_excel_response(content, "member_import_template.xlsx")
    except ImportError as exc:
        admin_obj.message_user(request, str(exc), level="error")
        return HttpResponseRedirect(reverse("admin:authn_member_changelist"))


def export_excel_view(admin_obj, request):
    # Member records are PII; ``admin_view`` only checks is_staff, so re-check
    # per-app access before exporting the whole member list.
    if not admin_obj.has_view_permission(request):
        raise PermissionDenied("You do not have permission to export members.")
    return export_members_response(admin_obj.get_queryset(request))
