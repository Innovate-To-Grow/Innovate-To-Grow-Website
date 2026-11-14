"""Where a submitted add / change / delete waits for its confirmation: the session (one slot per model), with its
uploads and secret fields in the cache."""

import uuid

from django.core.cache import cache

from .post_data import extract_sensitive_post_data, serialize_post_data

SESSION_KEY_PREFIX = "_admin_pending_change"
CACHE_FILE_PREFIX = "admin_confirm_file_"
CACHE_FILE_TTL = 600
CACHE_SECRET_SUFFIX = "__secret_post"  # nosec B105 — cache-key suffix, not a password
EXPIRED_UPLOAD_ERROR = "The uploaded file is no longer available — please re-upload it and save again."
EXPIRED_PENDING_ERROR = "This confirmation expired before it was submitted. Please make your change again."


def _rewind(uploaded_file):
    """Best-effort seek to the start of an upload that an earlier reader may have consumed."""
    try:
        uploaded_file.seek(0)
    except (AttributeError, OSError, ValueError):
        pass


class PendingChangeMixin:
    def _session_key(self):
        return f"{SESSION_KEY_PREFIX}_{self.opts.app_label}_{self.opts.model_name}"

    @staticmethod
    def _discard_pending_confirmation(request, session_key):
        """Remove pending confirmation state and any uploads it owns."""
        pending = request.session.pop(session_key, None)
        if not isinstance(pending, dict):
            return
        secret_key = pending.get("secret_key")
        if secret_key:
            cache.delete(secret_key)
        file_keys = pending.get("file_keys", {})
        if not isinstance(file_keys, dict):
            return
        for cache_key in file_keys.values():
            cache.delete(cache_key)

    def _stash_pending_change(self, request, *, action_type, object_id, object_repr, form_url, diff) -> None:
        """Hold the validated submission until it is confirmed: uploads and secrets in the cache, the rest in the session."""
        token = str(uuid.uuid4())
        file_keys = {}
        for field_name, uploaded_file in request.FILES.items():
            cache_key = f"{CACHE_FILE_PREFIX}{token}_{field_name}"
            # ``form.is_valid()`` above has already read these streams (a widget may read them more
            # than once), so rewind before copying — otherwise the cached payload is empty and the
            # confirmed save writes a zero-byte file over the stored one.
            _rewind(uploaded_file)
            content = uploaded_file.read()
            _rewind(uploaded_file)
            cache.set(
                cache_key,
                {
                    "name": uploaded_file.name,
                    "content": content,
                    "content_type": uploaded_file.content_type,
                },
                CACHE_FILE_TTL,
            )
            file_keys[field_name] = cache_key

        # Passwords and similar secrets are held in the cache (short TTL, deleted on use) instead of
        # the session: sessions are DB-backed here with an 8-hour lifetime, so a plaintext password in
        # ``post_data`` sat at rest in ``django_session`` long after the admin abandoned the page.
        secret_post = extract_sensitive_post_data(request.POST)
        secret_key = ""  # nosec B105 — cache key for the pending secrets, not a password
        if secret_post:
            secret_key = f"{CACHE_FILE_PREFIX}{token}{CACHE_SECRET_SUFFIX}"
            cache.set(secret_key, secret_post, CACHE_FILE_TTL)

        request.session[self._session_key()] = {
            "token": token,
            "action": action_type,
            "object_id": object_id,
            "object_repr": object_repr,
            "form_url": form_url,
            "post_data": serialize_post_data(request.POST),
            "file_keys": file_keys,
            "secret_key": secret_key,
            "diff": diff,
        }
