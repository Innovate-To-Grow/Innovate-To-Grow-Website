"""Members → Import: Upload → Review → Confirm → Result.

``admin_site.admin_view`` only checks ``is_staff``, so every view here re-checks authn-app access, as every custom
member tool does. Only the uploader or an I2G Master may change a batch's choices, apply it or discard it; other
authn admins see it read-only. Nothing touches member data before the confirmed apply.
"""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from ....models import MemberImportBatch
from ....services.members.import_.review import (
    create_batch,
    purge_member_imports,
    save_choices,
)
from ....services.members.import_.review.staging.batches import (
    import_setting,
    is_expired,
    mark_expired,
    repeat_uploads,
)
from ....services.members.import_.review.staging.saving import StaleVersion
from ....services.members.import_.review.staging.selection import ForgedSelection
from ....services.members.import_.workbook.reader import read_upload
from .context import review_sections
from .forms import MemberImportForm, parse_review_post
from .rights import (
    Status,
    _require_access,
    _require_edit,
    analysis_context,
    can_edit,
)


def _page(admin_obj, request, template: str, title: str, **context):
    return render(
        request,
        f"admin/authn/member_import/{template}",
        {**admin_obj.admin_site.each_context(request), "title": title, "opts": admin_obj.model._meta, **context},
    )


def _url(name: str, batch=None) -> str:
    return reverse(f"admin:authn_member_import_{name}", args=[batch.pk] if batch is not None else [])


def upload_view(admin_obj, request):
    _require_access(admin_obj, request)
    # Retention runs on each visit too (bounded), so imports are purged even when the worker is off.
    purge_member_imports(max_passes=1)
    can_update = admin_obj.has_change_permission(request)
    form = MemberImportForm(can_update=can_update)
    repeats = []
    if request.method == "POST":
        form = MemberImportForm(request.POST, request.FILES, can_update=can_update)
        if form.is_valid():
            batch, repeats = _stage_upload(admin_obj, request, form)
            if batch is not None:
                return HttpResponseRedirect(_url("review", batch))
    in_review = MemberImportBatch.objects.filter(status=Status.REVIEW, expires_at__gt=timezone.now())
    if not request.user.is_superuser:
        in_review = in_review.filter(created_by=request.user)
    return _page(
        admin_obj,
        request,
        "import_excel.html",
        "Import Members",
        form=form,
        repeats=repeats,
        in_review=in_review.select_related("created_by")[:20],
        max_rows=import_setting("max_rows"),
        lifetime_hours=import_setting("batch_lifetime_hours"),
    )


def _stage_upload(admin_obj, request, form):
    """``(batch, repeats)``: the staged batch, or None with the earlier uploads of the same file to warn about."""
    read = read_upload(
        form.cleaned_data["excel_file"],
        max_rows=import_setting("max_rows"),
        max_rows_read=import_setting("max_rows_read"),
    )
    if read.error or not read.rows:
        form.add_error("excel_file", read.error or "The sheet has no member rows below its header row.")
        return None, []
    repeats = repeat_uploads(read.file_sha256)
    if repeats and not form.cleaned_data["upload_anyway"]:
        return None, repeats
    mode = form.cleaned_data["mode"]
    batch = create_batch(
        read,
        user=request.user,
        mode=mode,
        password=form.cleaned_data.get("set_password") or "",
        ctx=analysis_context(admin_obj, request, mode),
    )
    return batch, repeats


def review_view(admin_obj, request, batch_id):
    _require_access(admin_obj, request)
    batch = get_object_or_404(MemberImportBatch, pk=batch_id)
    if is_expired(batch):
        mark_expired(batch)
    if batch.status != Status.REVIEW:
        return HttpResponseRedirect(_url("result", batch))
    editable = can_edit(request, batch)
    if request.method == "POST":
        return _save(admin_obj, request, batch)
    sections = review_sections(batch)
    return _page(
        admin_obj,
        request,
        "import_review.html",
        f"Review import: {batch.file_name}",
        batch=batch,
        editable=editable,
        repeats=repeat_uploads(batch.file_sha256, exclude=batch.pk),
        **sections,
    )


def _save(admin_obj, request, batch):
    _require_edit(admin_obj, request, batch)
    row_numbers = list(batch.rows.values_list("row_number", flat=True))
    posted, command, bulk, version = parse_review_post(request.POST, row_numbers)
    try:
        outcome = save_choices(
            batch,
            user=request.user,
            version=version if version is not None else -1,
            posted=posted,
            command=command,
            bulk=bulk,
        )
    except ForgedSelection as exc:
        messages.error(request, f"Nothing was saved: {exc}.")
        return HttpResponseRedirect(_url("review", batch))
    except StaleVersion as exc:
        messages.warning(request, str(exc))
        return HttpResponseRedirect(_url("review", batch))
    if command == "continue":
        return HttpResponseRedirect(_url("confirm", batch))
    getattr(messages, outcome.level)(request, outcome.message)
    for line in outcome.kept[:20]:
        messages.info(request, line)
    return HttpResponseRedirect(_url("review", batch))
