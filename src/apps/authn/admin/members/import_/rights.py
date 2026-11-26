from django.core.exceptions import PermissionDenied

from ....models import MemberImportBatch
from ....services.members.import_.review.analysis import Context

Status = MemberImportBatch.Status


def _require_access(admin_obj, request) -> None:
    """Only an Admin uses the import: ``admin_site.admin_view`` checks ``is_staff`` only, so every view checks again."""
    if not admin_obj.has_view_permission(request):
        raise PermissionDenied("You do not have permission to import members.")


def analysis_context(admin_obj, request, mode: str) -> Context:
    """The context a batch is analysed and applied with: the upload's mode and the acting Admin.

    Every Admin may change, apply or discard any batch. The acting Admin is what the lockout rules check a
    deactivation against: the uploader's when the batch is staged, the applying Admin's when it is applied.
    """
    return Context(mode=mode, can_update=admin_obj.has_change_permission(request), actor=request.user)


def batch_context(admin_obj, request, batch: MemberImportBatch) -> Context:
    return analysis_context(admin_obj, request, batch.mode)
