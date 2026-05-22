import json
import logging
import uuid

from django.contrib import messages
from django.contrib.admin import helpers
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponseBase, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.http import unquote

from .confirm_on_save_utils import (
    compute_add_diff,
    compute_change_diff,
    compute_delete_diff,
    deserialize_post_data,
    serialize_post_data,
)

logger = logging.getLogger(__name__)

SESSION_KEY = "_admin_pending_change"
SESSION_ACTION_KEY = "_admin_pending_action"
CACHE_FILE_PREFIX = "admin_confirm_file_"
CACHE_FILE_TTL = 600


class ConfirmOnSaveMixin:
    require_confirmation = True
    actions_no_confirmation = []

    def get_confirmation_word(self, obj=None):
        return self.opts.verbose_name

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

        if "_confirmed_save" in request.POST:
            return self._execute_confirmed_save(request, object_id, form_url, extra_context)

        add = object_id is None
        if not add:
            obj = self.get_object(request, unquote(object_id))
            if obj is None:
                return super().changeform_view(request, object_id, form_url, extra_context)
        else:
            obj = None

        ModelForm = self.get_form(request, obj, change=not add)
        form = ModelForm(request.POST, request.FILES, instance=obj)

        if not form.is_valid():
            return super().changeform_view(request, object_id, form_url, extra_context)

        if add:
            diff = compute_add_diff(form)
            action_type = "add"
            object_repr = str(form.cleaned_data.get("name", "") or self.opts.verbose_name)
        else:
            diff = compute_change_diff(self.model, obj.pk, form)
            action_type = "change"
            object_repr = str(obj)

        if not diff and action_type == "change":
            return super().changeform_view(request, object_id, form_url, extra_context)

        token = str(uuid.uuid4())
        file_keys = {}
        for field_name, uploaded_file in request.FILES.items():
            cache_key = f"{CACHE_FILE_PREFIX}{token}_{field_name}"
            cache.set(
                cache_key,
                {
                    "name": uploaded_file.name,
                    "content": uploaded_file.read(),
                    "content_type": uploaded_file.content_type,
                },
                CACHE_FILE_TTL,
            )
            file_keys[field_name] = cache_key

        request.session[SESSION_KEY] = {
            "token": token,
            "action": action_type,
            "object_id": object_id,
            "object_repr": object_repr,
            "form_url": form_url,
            "post_data": serialize_post_data(request.POST),
            "file_keys": file_keys,
            "diff": diff,
        }

        confirm_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_confirm_change")
        return HttpResponseRedirect(confirm_url)

    def delete_view(self, request, object_id, extra_context=None):
        if request.method != "POST" or self._should_skip_confirmation(request):
            return super().delete_view(request, object_id, extra_context)

        if "_confirmed_delete" in request.POST:
            return self._execute_confirmed_delete(request, object_id, extra_context)

        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return super().delete_view(request, object_id, extra_context)

        diff = compute_delete_diff(obj)
        token = str(uuid.uuid4())

        request.session[SESSION_KEY] = {
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
        pending = request.session.get(SESSION_KEY)
        if not pending:
            messages.error(request, "No pending change found. Please try again.")
            changelist_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist")
            return HttpResponseRedirect(changelist_url)

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
            "confirmation_word_json": json.dumps(confirmation_word),
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
        return reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist")

    def _do_confirmed_save(self, request, pending):
        from django.utils.datastructures import MultiValueDict

        post_data = deserialize_post_data(pending["post_data"])
        post_data["_confirmed_save"] = ["1"]

        original_post = request.POST
        original_files = request._files if hasattr(request, "_files") else request.FILES
        request.POST = post_data

        files = MultiValueDict()
        for field_name, cache_key in pending.get("file_keys", {}).items():
            file_data = cache.get(cache_key)
            if file_data:
                files[field_name] = SimpleUploadedFile(
                    name=file_data["name"],
                    content=file_data["content"],
                    content_type=file_data["content_type"],
                )
                cache.delete(cache_key)
        request._files = files

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

        del request.session[SESSION_KEY]

        self._send_change_notification(request, pending)
        return response

    def _do_confirmed_delete(self, request, pending):
        post_data = deserialize_post_data(pending["post_data"])
        post_data["_confirmed_delete"] = ["1"]

        original_post = request.POST
        request.POST = post_data

        try:
            response = super().delete_view(request, pending["object_id"], None)
        finally:
            request.POST = original_post

        del request.session[SESSION_KEY]

        self._send_change_notification(request, pending)
        return response

    def _execute_confirmed_save(self, request, object_id, form_url, extra_context):
        post = request.POST.copy()
        del post["_confirmed_save"]
        request.POST = post
        return super().changeform_view(request, object_id, form_url, extra_context)

    def _execute_confirmed_delete(self, request, object_id, extra_context):
        post = request.POST.copy()
        del post["_confirmed_delete"]
        request.POST = post
        return super().delete_view(request, object_id, extra_context)

    def _send_change_notification(self, request, pending):
        from core.admin.notifications import notify_staff_of_action

        action_type = pending["action"]
        action_verb = {"add": "Added", "change": "Changed", "delete": "Deleted"}.get(action_type, "Modified")
        action_desc = f"{action_verb} {self.opts.verbose_name}: {pending['object_repr']}"

        summary = []
        diff = pending.get("diff", [])
        for item in diff[:10]:
            if action_type == "delete":
                summary.append({"label": item["label"], "value": item.get("value", "-")})
            elif action_type == "add":
                summary.append({"label": item["label"], "value": item.get("new_value", "-")})
            else:
                old = item.get("old_value", "-")
                new = item.get("new_value", "-")
                summary.append({"label": item["label"], "value": f"{old} → {new}"})

        admin_url = None
        if action_type != "delete" and pending.get("object_id"):
            try:
                admin_url = request.build_absolute_uri(
                    reverse(
                        f"admin:{self.opts.app_label}_{self.opts.model_name}_change",
                        args=[pending["object_id"]],
                    )
                )
            except Exception:
                logger.debug("Could not build admin URL for %s", pending.get("object_id"))

        notify_staff_of_action(
            actor=request.user,
            action=action_desc,
            summary=summary,
            admin_url=admin_url,
        )

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

        func, name, description = actions[action_name]

        try:
            description_str = str(description) % {"verbose_name_plural": self.opts.verbose_name_plural}
        except (KeyError, TypeError, ValueError):
            description_str = str(description)

        request.session[SESSION_ACTION_KEY] = {
            "token": str(uuid.uuid4()),
            "action_name": action_name,
            "action_description": description_str,
            "selected_pks": selected,
            "select_across": select_across,
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
        pending = request.session.get(SESSION_ACTION_KEY)
        if not pending:
            messages.error(request, "No pending action found. Please try again.")
            changelist_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist")
            return HttpResponseRedirect(changelist_url)

        confirmation_word = self.get_action_confirmation_word(pending["action_name"])

        if request.method == "POST":
            typed_word = request.POST.get("confirmation_word", "").strip()
            if typed_word.lower() != confirmation_word.lower():
                messages.error(request, f'Please type "{confirmation_word}" exactly to confirm.')
            else:
                return self._execute_confirmed_action(request, pending)

        selected_pks = pending["selected_pks"]
        select_across = pending["select_across"]
        item_count = self.model.objects.count() if select_across else len(selected_pks)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Confirm Action: {pending['action_description']}",
            "action_description": pending["action_description"],
            "action_name": pending["action_name"],
            "model_name": self.opts.verbose_name,
            "model_name_plural": self.opts.verbose_name_plural,
            "item_count": item_count,
            "confirmation_word": confirmation_word,
            "confirmation_word_json": json.dumps(confirmation_word),
            "token": pending["token"],
            "cancel_url": reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist"),
        }
        return TemplateResponse(request, "admin/core/confirm_action.html", context)

    def _execute_confirmed_action(self, request, pending):
        action_name = pending["action_name"]
        actions = self.get_actions(request)
        if action_name not in actions:
            messages.error(request, "Action no longer available.")
            del request.session[SESSION_ACTION_KEY]
            return HttpResponseRedirect(reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist"))

        func = actions[action_name][0]
        selected_pks = pending["selected_pks"]
        select_across = pending["select_across"]

        queryset = self.model.objects.all()
        if not select_across:
            queryset = queryset.filter(pk__in=selected_pks)

        original_post = request.POST
        if action_name == "delete_selected":
            post = request.POST.copy()
            post["post"] = "yes"
            request.POST = post

        try:
            response = func(self, request, queryset)
        finally:
            request.POST = original_post

        del request.session[SESSION_ACTION_KEY]

        self._send_action_notification(request, pending)

        if isinstance(response, HttpResponseBase):
            return response

        changelist_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist")
        return HttpResponseRedirect(changelist_url)

    def _send_action_notification(self, request, pending):
        from core.admin.notifications import notify_staff_of_action

        item_count = "all" if pending["select_across"] else str(len(pending["selected_pks"]))
        action_desc = f"{pending['action_description']} ({item_count} {self.opts.verbose_name_plural})"

        try:
            admin_url = request.build_absolute_uri(
                reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist")
            )
        except Exception:
            admin_url = None

        notify_staff_of_action(
            actor=request.user,
            action=action_desc,
            summary=[
                {"label": "Action", "value": pending["action_description"]},
                {"label": "Items affected", "value": item_count},
                {"label": "Model", "value": str(self.opts.verbose_name)},
            ],
            admin_url=admin_url,
        )
