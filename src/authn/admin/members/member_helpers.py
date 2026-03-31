from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from .forms import MemberImportForm


def get_primary_email_display(member):
    return member.get_primary_email() or "-"


def get_full_name_display(member):
    return member.get_full_name() or "-"


def activate_members(admin_obj, request, queryset):
    updated = queryset.update(is_active=True)
    admin_obj.message_user(request, f"{updated} member(s) activated.")


def deactivate_members(admin_obj, request, queryset):
    updated = queryset.update(is_active=False)
    admin_obj.message_user(request, f"{updated} member(s) deactivated.")


def build_excel_response(content, filename):
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_members_response(queryset):
    from django.utils import timezone

    from ...services.export_members import export_members_to_excel

    content = export_members_to_excel(queryset)
    filename = f"members_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return build_excel_response(content, filename)


def import_excel_view(admin_obj, request):
    from ...services.import_members import import_members_from_excel

    context = build_import_context(admin_obj, request, MemberImportForm(), result=None)
    if request.method != "POST":
        return render(request, "admin/authn/member/import_excel.html", context)

    form = MemberImportForm(request.POST, request.FILES)
    context["form"] = form
    if form.is_valid():
        result = import_members_from_excel(
            file=form.cleaned_data["excel_file"],
            default_password=form.cleaned_data.get("set_password") or None,
            update_existing=form.cleaned_data.get("update_existing", False),
        )
        context["result"] = result
        if result.success:
            message = (
                f"Import complete: {result.created_count} created, "
                f"{result.updated_count} updated, "
                f"{result.skipped_count} skipped"
            )
            if result.errors:
                message += f", {len(result.errors)} error(s)"
            admin_obj.message_user(request, message, level="success" if not result.errors else "warning")

    return render(request, "admin/authn/member/import_excel.html", context)


def download_template_view(admin_obj, request):
    from ...services.import_members import generate_template_excel

    try:
        content = generate_template_excel()
        return build_excel_response(content, "member_import_template.xlsx")
    except ImportError as exc:
        admin_obj.message_user(request, str(exc), level="error")
        return HttpResponseRedirect(reverse("admin:authn_member_changelist"))


def export_excel_view(admin_obj, request):
    return export_members_response(admin_obj.get_queryset(request))


def build_import_context(admin_obj, request, form, result):
    return {
        **admin_obj.admin_site.each_context(request),
        "title": "Import Members",
        "opts": admin_obj.model._meta,
        "form": form,
        "result": result,
    }
