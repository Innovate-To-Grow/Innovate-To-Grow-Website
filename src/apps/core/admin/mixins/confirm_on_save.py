import uuid

from django.contrib import messages
from django.contrib.admin import helpers
from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.contrib.admin.options import TO_FIELD_VAR
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.formsets import all_valid
from django.http import HttpResponseBase, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.http import unquote

from .confirm_on_save_utils import (
    compute_add_diff,
    compute_change_diff,
    compute_delete_diff,
    compute_formsets_diff,
    deserialize_post_data,
    extract_sensitive_post_data,
    serialize_post_data,
)

SESSION_KEY_PREFIX = "_admin_pending_change"
SESSION_ACTION_KEY_PREFIX = "_admin_pending_action"
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


class ConfirmOnSaveMixin:
    require_confirmation = True
    actions_no_confirmation = []

    def _session_key(self):
        return f"{SESSION_KEY_PREFIX}_{self.opts.app_label}_{self.opts.model_name}"

    def _session_action_key(self):
        return f"{SESSION_ACTION_KEY_PREFIX}_{self.opts.app_label}_{self.opts.model_name}"

    def _changelist_url(self):
        return reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist")

    def _invalid_confirmation_token_response(self, request, session_key):
        # Do NOT discard the pending state here. There is one slot per model, so a second submission
        # (another tab, or an autosave tick) replaces it; destroying the replacement on a stale tab's
        # token mismatch threw away the edits the admin was actually about to confirm.
        messages.error(request, "Invalid confirmation token. Please start over.")
        return HttpResponseRedirect(self._changelist_url())

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

    def get_confirmation_word(self, obj=None):
        return self.opts.verbose_name

    # Fold inline changes into the diff. Without this an edit that touched only inlines produced an
    # empty diff, so the ``if not diff`` short-circuit below committed it with no confirmation at all —
    # and when the main form *did* change, the admin typed the confirmation word to approve a diff that
    # listed none of the inline rows they had actually added or deleted.
    include_inlines_in_confirmation_diff = True

    def get_confirmation_diff(self, request, obj, form, formsets, action_type):
        """Return the serializable diff shown before saving an admin form."""
        if action_type == "add":
            diff = compute_add_diff(form)
        else:
            diff = compute_change_diff(self.model, obj.pk, form)
        if self.include_inlines_in_confirmation_diff:
            diff = diff + compute_formsets_diff(formsets)
        return diff

    def get_urls(self):
        custom = [
            path(
                "confirm-change/",
                self.admin_site.admin_view(self._confirm_change_view),
                name=f"{self.opts.app_label}_{self.opts.model_name}_confirm_change",
            ),
            path(
                "confirm-action/",
                self.admin_site.admin_view(self._confirm_action_view),
                name=f"{self.opts.app_label}_{self.opts.model_name}_confirm_action",
            ),
        ]
        return custom + super().get_urls()

    def _should_skip_confirmation(self, request):
        if not self.require_confirmation:
            return True
        from django.conf import settings
        from django.contrib.admin.options import IS_POPUP_VAR

        if not getattr(settings, "ADMIN_REQUIRE_CONFIRMATION", True):
            return True
        if IS_POPUP_VAR in request.POST or IS_POPUP_VAR in request.GET:
            return True
        if request.POST.get("_autosave"):
            return True
        return False

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if request.method != "POST" or self._should_skip_confirmation(request):
            return super().changeform_view(request, object_id, form_url, extra_context)

        # A new submission supersedes any abandoned confirmation for this
        # model. Clear it before validation so an invalid replacement cannot
        # leave an older payload available at the confirmation URL.
        self._discard_pending_confirmation(request, self._session_key())

        to_field = request.POST.get(TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
        if to_field and not self.to_field_allowed(request, to_field):
            raise DisallowedModelAdminToField(f"The field {to_field} cannot be referenced.")

        if "_saveasnew" in request.POST:
            object_id = None

        add = object_id is None
        if add:
            if not self.has_add_permission(request):
                raise PermissionDenied
            obj = None
        else:
            obj = self.get_object(request, unquote(object_id), to_field)
            if not self.has_change_permission(request, obj):
                raise PermissionDenied
            if obj is None:
                return super().changeform_view(request, object_id, form_url, extra_context)

        ModelForm = self.get_form(request, obj, change=not add)
        form = ModelForm(request.POST, request.FILES, instance=obj)
        formsets, _inline_instances = self._create_formsets(
            request,
            form.instance,
            change=not add,
        )

        form_valid = form.is_valid()
        formsets_valid = all_valid(formsets)
        if not form_valid or not formsets_valid:
            return super().changeform_view(request, object_id, form_url, extra_context)

        if add:
            action_type = "add"
            object_repr = str(form.cleaned_data.get("name", "") or self.opts.verbose_name)
        else:
            action_type = "change"
            object_repr = str(obj)

        diff = self.get_confirmation_diff(request, obj, form, formsets, action_type)

        if not diff and action_type == "change":
            return super().changeform_view(request, object_id, form_url, extra_context)

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

        confirm_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_confirm_change")
        return HttpResponseRedirect(confirm_url)

    def delete_view(self, request, object_id, extra_context=None):
        if request.method != "POST" or self._should_skip_confirmation(request):
            return super().delete_view(request, object_id, extra_context)

        self._discard_pending_confirmation(request, self._session_key())

        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return super().delete_view(request, object_id, extra_context)

        diff = compute_delete_diff(obj)
        token = str(uuid.uuid4())

        request.session[self._session_key()] = {
            "token": token,
            "action": "delete",
            "object_id": object_id,
            "object_repr": str(obj),
            "form_url": "",
            "post_data": serialize_post_data(request.POST),
            "file_keys": {},
            "diff": diff,
        }

        confirm_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_confirm_change")
        return HttpResponseRedirect(confirm_url)

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

    # --- Bulk action confirmation ---

    def response_action(self, request, queryset):
        if self._should_skip_confirmation(request):
            return super().response_action(request, queryset)

        if "_confirmed_action" in request.POST:
            return super().response_action(request, queryset)

        try:
            action_index = int(request.POST.get("index", 0))
        except ValueError:
            action_index = 0

        data = request.POST.copy()
        data.pop(helpers.ACTION_CHECKBOX_NAME, None)
        data.pop("index", None)

        try:
            data.update({"action": data.getlist("action")[action_index]})
        except IndexError:
            return super().response_action(request, queryset)

        action_form = self.action_form(data, auto_id=None)
        action_form.fields["action"].choices = self.get_action_choices(request)

        if not action_form.is_valid():
            return super().response_action(request, queryset)

        action_name = action_form.cleaned_data["action"]
        select_across = action_form.cleaned_data["select_across"]

        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
        if not selected and not select_across:
            return super().response_action(request, queryset)

        if self._action_skips_confirmation(action_name, request):
            return super().response_action(request, queryset)

        actions = self.get_actions(request)
        if action_name not in actions:
            return super().response_action(request, queryset)

        _func, _name, description = actions[action_name]

        try:
            description_str = str(description) % {"verbose_name_plural": self.opts.verbose_name_plural}
        except (KeyError, TypeError, ValueError):
            description_str = str(description)

        if select_across:
            action_queryset = queryset
        else:
            action_queryset = queryset.filter(pk__in=selected)

        action_pks = [str(pk) for pk in action_queryset.values_list("pk", flat=True)]
        if not action_pks:
            return super().response_action(request, queryset)

        request.session[self._session_action_key()] = {
            "token": str(uuid.uuid4()),
            "action_name": action_name,
            "action_description": description_str,
            "selected_pks": selected,
            "select_across": select_across,
            "queryset_pks": action_pks,
            "item_count": len(action_pks),
            "post_data": serialize_post_data(request.POST),
        }

        confirm_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_confirm_action")
        return HttpResponseRedirect(confirm_url)

    def _action_skips_confirmation(self, action_name, request):
        exempt = set()
        for cls in type(self).__mro__:
            exempt.update(getattr(cls, "actions_no_confirmation", []))
        if action_name in exempt:
            return True
        actions = self.get_actions(request)
        if action_name in actions:
            func = actions[action_name][0]
            if getattr(func, "no_confirmation", False):
                return True
        return False

    def get_action_confirmation_word(self, action_name):
        return self.opts.verbose_name

    def _confirm_action_view(self, request):
        # See _confirm_change_view: gate the bulk-action confirmation on per-app
        # access (execution re-checks via response_action / the action itself).
        if not self.has_view_permission(request):
            raise PermissionDenied
        session_key = self._session_action_key()
        pending = request.session.get(session_key)
        if not pending:
            messages.error(request, "No pending action found. Please try again.")
            return HttpResponseRedirect(self._changelist_url())

        if request.method == "POST" and request.POST.get("token") != pending.get("token"):
            return self._invalid_confirmation_token_response(request, session_key)

        confirmation_word = self.get_action_confirmation_word(pending["action_name"])

        if request.method == "POST":
            typed_word = request.POST.get("confirmation_word", "").strip()
            if typed_word.lower() != confirmation_word.lower():
                messages.error(request, f'Please type "{confirmation_word}" exactly to confirm.')
            else:
                return self._execute_confirmed_action(request, pending)

        item_count = pending.get("item_count", len(pending["selected_pks"]))

        context = {
            **self.admin_site.each_context(request),
            "title": f"Confirm Action: {pending['action_description']}",
            "action_description": pending["action_description"],
            "action_name": pending["action_name"],
            "model_name": self.opts.verbose_name,
            "model_name_plural": self.opts.verbose_name_plural,
            "item_count": item_count,
            "confirmation_word": confirmation_word,
            "token": pending["token"],
            "cancel_url": self._changelist_url(),
        }
        return TemplateResponse(request, "admin/core/confirm_action.html", context)

    def _execute_confirmed_action(self, request, pending):
        action_name = pending["action_name"]
        actions = self.get_actions(request)
        if action_name not in actions:
            messages.error(request, "Action no longer available.")
            request.session.pop(self._session_action_key(), None)
            return HttpResponseRedirect(self._changelist_url())

        func = actions[action_name][0]
        queryset_pks = pending.get("queryset_pks")
        if queryset_pks is None:
            queryset_pks = pending["selected_pks"] if not pending["select_across"] else []
        queryset = self.get_queryset(request).filter(pk__in=queryset_pks)

        original_post = request.POST
        if action_name == "delete_selected":
            post = request.POST.copy()
            post["post"] = "yes"
            request.POST = post

        try:
            response = func(self, request, queryset)
        finally:
            request.POST = original_post

        request.session.pop(self._session_action_key(), None)

        if isinstance(response, HttpResponseBase):
            return response

        return HttpResponseRedirect(self._changelist_url())
