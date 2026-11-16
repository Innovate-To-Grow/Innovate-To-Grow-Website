"""The Member admin's own pages: import, template and export downloads, impersonation and the profile image."""

import logging
from urllib.parse import unquote

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import path

from ....models import ImpersonationToken
from ....services.members.accounts.profile_image import ALLOWED_CONTENT_TYPES, ProfileImageError, split_data_uri
from ..import_ import confirm_views
from ..import_ import views as import_views
from .helpers import (
    download_template_view,
    export_excel_view,
)

logger = logging.getLogger("apps.authn.admin.members.member")  # its log name before the move


class MemberAdminViewsMixin:
    def get_urls(self):
        custom_urls = [
            path("import-excel/", self.admin_site.admin_view(self.import_excel_view), name="authn_member_import_excel"),
            *self._import_review_urls(),
            path(
                "import-template/",
                self.admin_site.admin_view(self.download_template_view),
                name="authn_member_import_template",
            ),
            path("export-excel/", self.admin_site.admin_view(self.export_excel_view), name="authn_member_export_excel"),
            path(
                "<path:object_id>/impersonate/",
                self.admin_site.admin_view(self.impersonate_view),
                name="authn_member_impersonate",
            ),
            path(
                "<path:object_id>/profile-image/",
                self.admin_site.admin_view(self.profile_image_view),
                name="authn_member_profile_image",
            ),
        ]
        return custom_urls + super().get_urls()

    def profile_image_view(self, request, object_id):
        """Stream a member's stored profile image so the change form never inlines it.

        ``profile_image`` holds a base64 ``data:`` URI in a TextField; rendering it inside an
        ``<img src>`` made the change page grow with the image and truncate mid-form. Like every other
        custom admin URL here, ``admin_site.admin_view`` only enforces ``is_staff``, so re-check
        per-app access.
        """
        if not self.has_view_permission(request):
            raise PermissionDenied("You do not have permission to view members.")
        member = self.get_object(request, unquote(str(object_id)))
        if member is None or not member.profile_image:
            raise Http404("This member has no profile image.")
        try:
            raw, mime = split_data_uri(member.profile_image)
        except ProfileImageError as exc:
            raise Http404("Stored profile image could not be decoded.") from exc

        response = HttpResponse(raw, content_type=mime)
        if mime not in ALLOWED_CONTENT_TYPES:
            # Legacy rows could hold any client-supplied type; never let one render inline.
            response["Content-Type"] = "application/octet-stream"
            response["Content-Disposition"] = f'attachment; filename="profile-{member.pk}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def impersonate_view(self, request, object_id):
        # ``admin_site.admin_view`` only enforces is_staff, so this custom URL must
        # re-check authorization itself (Django never runs the per-app model
        # permissions for a standalone admin view). Require authn-app access, and
        # never let a non-superuser account be impersonated into a privileged one:
        # impersonation is an end-user support tool, and minting a token for a
        # staff/superuser account would be a privilege-escalation vector.
        if not self.has_change_permission(request):
            raise PermissionDenied("You do not have permission to impersonate members.")
        # POST-only: minting a token is a state change, and on GET Django performs no CSRF check,
        # so a cross-site navigation could make an admin issue (and burn) impersonation credentials.
        if request.method != "POST":
            raise PermissionDenied("Impersonation must be started with a POST request.")
        # ``self.get_object`` swallows the ValidationError a non-UUID <path:object_id> would raise;
        # ``get_object_or_404`` only translates DoesNotExist and so returned a 500 instead of a 404.
        member = self.get_object(request, unquote(str(object_id)))
        if member is None:
            raise Http404("No member matches the given query.")
        if member.is_staff or member.is_superuser:
            raise PermissionDenied("Staff and superuser accounts cannot be impersonated.")
        token = ImpersonationToken.generate_token()
        ImpersonationToken.objects.create(token=token, member=member, created_by=request.user)
        logger.info("Administrator %s began impersonating member %s", request.user.id, member.id)
        frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
        return redirect(f"{frontend_url}/impersonate-login#token={token}")

    def _import_review_urls(self):
        """Review → Confirm → Result of one staged import (``import_views``)."""
        views = (
            ("import-excel/<uuid:batch_id>/review/", import_views.review_view, "authn_member_import_review"),
            ("import-excel/<uuid:batch_id>/confirm/", confirm_views.confirm_view, "authn_member_import_confirm"),
            ("import-excel/<uuid:batch_id>/discard/", confirm_views.discard_view, "authn_member_import_discard"),
            ("import-excel/<uuid:batch_id>/", confirm_views.result_view, "authn_member_import_result"),
        )
        return [path(route, self.admin_site.admin_view(self._bind(view)), name=name) for route, view, name in views]

    def _bind(self, view):
        def bound(request, *args, **kwargs):
            return view(self, request, *args, **kwargs)

        return bound

    def import_excel_view(self, request):
        return import_views.upload_view(self, request)

    def download_template_view(self, request):
        return download_template_view(self, request)

    def export_excel_view(self, request):
        return export_excel_view(self, request)
