from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404

from ....models import MemberImportBatch
from ....services.members.import_.review import (
    apply_batch,
    discard_batch,
)
from ....services.members.import_.review.staging.batches import (
    is_expired,
    mark_expired,
)
from .context import review_sections
from .forms import ImportConfirmForm
from .rights import Status, _require_access, batch_context
from .summary_lines import confirm_lines, risky_lines
from .views import _page, _url


def confirm_view(admin_obj, request, batch_id):
    _require_access(admin_obj, request)
    batch = get_object_or_404(MemberImportBatch, pk=batch_id)
    if is_expired(batch):
        mark_expired(batch)
    if batch.status != Status.REVIEW:
        return HttpResponseRedirect(_url("result", batch))
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
    result = apply_batch(batch.pk, user=request.user, version=version, ctx=batch_context(admin_obj, request, batch))
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
        counts=(batch.summary or {}).get("outcomes", {}),
        risky=risky_lines((batch.summary or {}).get("risky", {})),
        primary_changed=bool((batch.summary or {}).get("risky", {}).get("primary_changes")),
    )


def discard_view(admin_obj, request, batch_id):
    _require_access(admin_obj, request)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    batch = get_object_or_404(MemberImportBatch, pk=batch_id)
    discard_batch(batch, request.user)
    messages.info(request, f"The import of {batch.file_name} was discarded. Nothing was written.")
    return HttpResponseRedirect(_url("excel"))
