from django.core.exceptions import PermissionDenied

from apps.core.utils.access import user_can_access_app, user_can_manage_member

from ....models import MemberImportBatch
from ....services.members.import_.review.analysis import Context

Status = MemberImportBatch.Status


APP_LABEL = "authn"


def _require_access(admin_obj, request) -> None:
    if not admin_obj.has_view_permission(request):
        raise PermissionDenied("You do not have permission to import members.")


def can_edit(request, batch: MemberImportBatch) -> bool:
    return request.user.is_superuser or batch.created_by_id == request.user.pk


def _require_edit(admin_obj, request, batch) -> None:
    _require_access(admin_obj, request)
    if not can_edit(request, batch):
        raise PermissionDenied("Only the admin who uploaded this import, or an I2G Master, may change it.")


def analysis_context(admin_obj, request, mode: str, uploader=None) -> Context:
    """The rights a batch is analysed and applied with: the acting admin's, intersected with the uploader's.

    So an I2G Master who applies another admin's import never lends it master rights: a staff or superuser row, a
    staff-status tick or a verification on a privileged account stays out of reach unless the uploader had the right
    too. An import whose uploader was deleted is never applied (``confirm_view``); it can be discarded or left to
    expire.
    """
    user = request.user
    actors = [user] if uploader is None or uploader.pk == user.pk else [user, uploader]
    return Context(
        mode=mode,
        is_master=all(actor.is_superuser for actor in actors),
        can_update=admin_obj.has_change_permission(request)
        and all(user_can_access_app(actor, APP_LABEL) for actor in actors),
        can_manage=lambda member: all(user_can_manage_member(actor, member) for actor in actors),
    )


def batch_context(admin_obj, request, batch: MemberImportBatch) -> Context:
    return analysis_context(admin_obj, request, batch.mode, uploader=batch.created_by)
