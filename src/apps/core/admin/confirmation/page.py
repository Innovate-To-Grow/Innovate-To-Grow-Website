"""The confirmation page of an admin add / change / delete, and the replay of the held submission once confirmed."""

from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from .pending import EXPIRED_PENDING_ERROR, EXPIRED_UPLOAD_ERROR
from .post_data import deserialize_post_data


class ChangeConfirmationPageMixin:
    def _confirm_change_view(self, request):
        # ``admin_view`` only enforces is_staff; re-check per-app access so a
        # staff member without this model's app cannot reach the change/delete
        # confirmation (and its data diff). Execution is additionally gated by
        # the underlying ``changeform_view``/``delete_view`` permission checks.
        if not self.has_view_permission(request):
            raise PermissionDenied
        session_key = self._session_key()
        pending = request.session.get(session_key)
        if not pending:
            messages.error(request, "No pending change found. Please try again.")
            return HttpResponseRedirect(self._changelist_url())

        if request.method == "POST" and request.POST.get("token") != pending.get("token"):
            return self._invalid_confirmation_token_response(request, session_key)

        confirmation_word = self.get_confirmation_word()

        if request.method == "POST":
            typed_word = request.POST.get("confirmation_word", "").strip()
            if typed_word.lower() != confirmation_word.lower():
                messages.error(
                    request,
                    f'Please type "{confirmation_word}" exactly to confirm.',
                )
            else:
                if pending["action"] == "delete":
                    return self._do_confirmed_delete(request, pending)
                return self._do_confirmed_save(request, pending)

        action_label = {
            "add": "Adding",
            "change": "Changing",
            "delete": "Deleting",
        }.get(pending["action"], "Modifying")

        context = {
            **self.admin_site.each_context(request),
            "title": f"Confirm {action_label} {self.opts.verbose_name}",
            "action_label": action_label,
            "action_type": pending["action"],
            "model_name": self.opts.verbose_name,
            "object_repr": pending["object_repr"],
            "diff": pending["diff"],
            "confirmation_word": confirmation_word,
            "token": pending["token"],
            "cancel_url": self._get_cancel_url(pending),
        }
        return TemplateResponse(request, "admin/core/confirm_change.html", context)

    def _get_cancel_url(self, pending):
        if pending["action"] == "delete" or pending["action"] == "change":
            object_id = pending["object_id"]
            return reverse(
                f"admin:{self.opts.app_label}_{self.opts.model_name}_change",
                args=[object_id],
            )
        return self._changelist_url()

    def _replay_path(self, pending):
        """The URL the replayed request should appear to target.

        Django's ``response_change`` branches on ``request.path`` for ``_continue``, so replaying with
        the confirm URL still set sent the admin back to ``/confirm-change/`` — where the pending entry
        had just been popped, producing "No pending change found" and a bounce to the changelist even
        though the save succeeded.
        """
        if pending["action"] == "add":
            return reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_add")
        return reverse(
            f"admin:{self.opts.app_label}_{self.opts.model_name}_change",
            args=[pending["object_id"]],
        )

    def _do_confirmed_save(self, request, pending):
        from django.utils.datastructures import MultiValueDict

        post_data = deserialize_post_data(pending["post_data"])
        secret_key = pending.get("secret_key")
        if secret_key:
            secrets = cache.get(secret_key)
            if not secrets:
                messages.error(request, EXPIRED_PENDING_ERROR)
                self._discard_pending_confirmation(request, self._session_key())
                return HttpResponseRedirect(self._get_cancel_url(pending))
            for key, values in secrets.items():
                post_data.setlist(key, values)
            cache.delete(secret_key)

        original_post = request.POST
        original_files = request._files if hasattr(request, "_files") else request.FILES
        original_path = request.path
        original_path_info = request.path_info
        request.POST = post_data

        files = MultiValueDict()
        for field_name, cache_key in pending.get("file_keys", {}).items():
            file_data = cache.get(cache_key)
            if not file_data:
                # The payload lives in the default cache, which falls back to a per-container file
                # cache when REDIS_URL is unset — so a task hop, a deploy, or sitting on the confirm
                # page past CACHE_FILE_TTL loses it. Fail loudly instead of saving a form with no file.
                messages.error(request, EXPIRED_UPLOAD_ERROR)
                self._discard_pending_confirmation(request, self._session_key())
                return HttpResponseRedirect(self._get_cancel_url(pending))
            files[field_name] = SimpleUploadedFile(
                name=file_data["name"],
                content=file_data["content"],
                content_type=file_data["content_type"],
            )
            cache.delete(cache_key)
        request._files = files
        request.path = request.path_info = self._replay_path(pending)

        try:
            response = super().changeform_view(
                request,
                pending["object_id"],
                pending["form_url"],
                None,
            )
        finally:
            request.POST = original_post
            request._files = original_files
            request.path = original_path
            request.path_info = original_path_info

        if isinstance(response, HttpResponseRedirect):
            request.session.pop(self._session_key(), None)
        return response

    def _do_confirmed_delete(self, request, pending):
        post_data = deserialize_post_data(pending["post_data"])

        original_post = request.POST
        request.POST = post_data

        try:
            response = super().delete_view(request, pending["object_id"], None)
        finally:
            request.POST = original_post

        if isinstance(response, HttpResponseRedirect):
            request.session.pop(self._session_key(), None)
        return response
