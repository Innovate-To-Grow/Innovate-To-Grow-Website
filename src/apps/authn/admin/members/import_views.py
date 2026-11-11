"""Members → Import: Upload → Review → Confirm → Result.

``admin_site.admin_view`` only checks ``is_staff``, so every view here re-checks authn-app access, as every custom
member tool does. Only the uploader or an I2G Master may change a batch's choices, apply it or discard it; other
authn admins see it read-only. Nothing touches member data before the confirmed apply.
"""

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from ...models import MemberImportBatch
from ...services.members.import_.reader import read_upload
from ...services.members.import_.review import (
    apply_batch,
    create_batch,
    discard_batch,
    purge_member_imports,
    save_choices,
)
from ...services.members.import_.review.analysis import Context
from ...services.members.import_.review.batches import (
    StaleVersion,
    import_setting,
    is_expired,
    mark_expired,
    repeat_uploads,
)
from ...services.members.import_.review.selection import ForgedSelection
from .import_context import confirm_lines, review_sections
from .import_forms import ImportConfirmForm, MemberImportForm, parse_review_post

Status = MemberImportBatch.Status


def _require_access(admin_obj, request) -> None:
    if not admin_obj.has_view_permission(request):
        raise PermissionDenied("You do not have permission to import members.")


def can_edit(request, batch: MemberImportBatch) -> bool:
    return request.user.is_superuser or batch.created_by_id == request.user.pk


def _require_edit(admin_obj, request, batch) -> None:
    _require_access(admin_obj, request)
    if not can_edit(request, batch):
        raise PermissionDenied("Only the admin who uploaded this import, or an I2G Master, may change it.")


def analysis_context(admin_obj, request, mode: str) -> Context:
    return Context(
        mode=mode,
        is_master=bool(request.user.is_superuser),
        can_update=admin_obj.has_change_permission(request),
        can_manage=lambda member: admin_obj.can_manage_target(request, member),
    )


def _page(admin_obj, request, template: str, title: str, **context):
    return render(
        request,
        f"admin/authn/member/{template}",
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
    read = read_upload(form.cleaned_data["excel_file"], max_rows=import_setting("max_rows"))
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


def confirm_view(admin_obj, request, batch_id):
    _require_access(admin_obj, request)
    batch = get_object_or_404(MemberImportBatch, pk=batch_id)
    if is_expired(batch):
        mark_expired(batch)
    if batch.status != Status.REVIEW:
        return HttpResponseRedirect(_url("result", batch))
    _require_edit(admin_obj, request, batch)
    require_text = getattr(settings, "ADMIN_REQUIRE_CONFIRMATION", True)
    sections = review_sections(batch)
    if sections["problems"]:
        messages.error(request, "Fix the problems listed at the top of the review before you confirm.")
        return HttpResponseRedirect(_url("review", batch))
    form = ImportConfirmForm(initial={"version": batch.choices_version}, require_text=require_text)
    if request.method == "POST":
        form = ImportConfirmForm(request.POST, require_text=require_text)
        if form.is_valid():
            return _apply(admin_obj, request, batch, form.cleaned_data["version"])
    return _page(
        admin_obj,
        request,
        "import_confirm.html",
        f"Confirm import: {batch.file_name}",
        batch=batch,
        form=form,
        require_text=require_text,
        **sections,
        **confirm_lines(sections["summary"]),
    )


def _apply(admin_obj, request, batch, version: int):
    result = apply_batch(
        batch.pk, user=request.user, version=version, ctx=analysis_context(admin_obj, request, batch.mode)
    )
    if result.status == "applied":
        batch.refresh_from_db()
        counts = (batch.summary or {}).get("outcomes", {})
        message = (
            f"Import complete: {counts.get('created', 0)} created, {counts.get('updated', 0)} updated, "
            f"{counts.get('skipped', 0) + counts.get('not_imported', 0)} skipped"
        )
        messages.success(request, message)
        return HttpResponseRedirect(_url("result", batch))
    if result.status == "already":
        messages.info(request, "This import was already applied or discarded.")
        return HttpResponseRedirect(_url("result", batch))
    level = messages.warning if result.status == "stale" else messages.error
    level(request, f"Nothing was imported. {result.message.rstrip('.')}.")
    return HttpResponseRedirect(_url("review", batch))


def result_view(admin_obj, request, batch_id):
    _require_access(admin_obj, request)
    batch = get_object_or_404(MemberImportBatch.objects.select_related("created_by", "applied_by"), pk=batch_id)
    if is_expired(batch):
        mark_expired(batch)
    rows = batch.rows.order_by("row_number").select_related("result_member", "chosen_by")
    return _page(
        admin_obj,
        request,
        "import_result.html",
        f"Member import: {batch.file_name}",
        batch=batch,
        rows=rows,
        editable=can_edit(request, batch),
        counts=(batch.summary or {}).get("outcomes", {}),
        risky=(batch.summary or {}).get("risky", {}),
    )


def discard_view(admin_obj, request, batch_id):
    _require_access(admin_obj, request)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    batch = get_object_or_404(MemberImportBatch, pk=batch_id)
    _require_edit(admin_obj, request, batch)
    discard_batch(batch, request.user)
    messages.info(request, f"The import of {batch.file_name} was discarded. Nothing was written.")
    return HttpResponseRedirect(_url("excel"))
