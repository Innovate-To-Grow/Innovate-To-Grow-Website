"""Type-to-confirm for admin bulk actions, and the confirmation plumbing every confirm flow shares."""

import uuid

from django.contrib import messages
from django.contrib.admin import helpers
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBase, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .confirm_on_save_utils import serialize_post_data

SESSION_ACTION_KEY_PREFIX = "_admin_pending_action"


class ConfirmActionMixin:
    require_confirmation = True
    actions_no_confirmation = []

    def _session_action_key(self):
        return f"{SESSION_ACTION_KEY_PREFIX}_{self.opts.app_label}_{self.opts.model_name}"

    def _changelist_url(self):
        return reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_changelist")

    def _invalid_confirmation_token_response(self, request, session_key):
        # Do NOT discard the pending state here. There is one slot per model, so a second submission
        # (from another tab) replaces it; destroying the replacement on a stale tab's token mismatch
        # threw away the edits the admin was actually about to confirm.
        messages.error(request, "Invalid confirmation token. Please start over.")
        return HttpResponseRedirect(self._changelist_url())

    def _should_skip_confirmation(self, request):
        if not self.require_confirmation:
            return True
        from django.conf import settings
        from django.contrib.admin.options import IS_POPUP_VAR

        if not getattr(settings, "ADMIN_REQUIRE_CONFIRMATION", True):
            return True
        if IS_POPUP_VAR in request.POST or IS_POPUP_VAR in request.GET:
            return True
        return False

    def get_urls(self):
        custom = [
            path(
                "confirm-action/",
                self.admin_site.admin_view(self._confirm_action_view),
                name=f"{self.opts.app_label}_{self.opts.model_name}_confirm_action",
            ),
        ]
        return custom + super().get_urls()

    def response_action(self, request, queryset):
        if self._should_skip_confirmation(request):
            return super().response_action(request, queryset)

        action_form = self._bound_action_form(request)
        if action_form is None or not action_form.is_valid():
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
        action_queryset = queryset if select_across else queryset.filter(pk__in=selected)
        action_pks = [str(pk) for pk in action_queryset.values_list("pk", flat=True)]
        if not action_pks:
            return super().response_action(request, queryset)

        request.session[self._session_action_key()] = {
            "token": str(uuid.uuid4()),
            "action_name": action_name,
            "action_description": self._action_description(description),
            "selected_pks": selected,
            "select_across": select_across,
            "queryset_pks": action_pks,
            "item_count": len(action_pks),
            "post_data": serialize_post_data(request.POST),
        }

        confirm_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_confirm_action")
        return HttpResponseRedirect(confirm_url)

    def _bound_action_form(self, request):
        """The changelist's action form bound to the chosen action (as Django does it); None if none was chosen."""
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
            return None
        action_form = self.action_form(data, auto_id=None)
        action_form.fields["action"].choices = self.get_action_choices(request)
        return action_form

    def _action_description(self, description) -> str:
        try:
            return str(description) % {"verbose_name_plural": self.opts.verbose_name_plural}
        except (KeyError, TypeError, ValueError):
            return str(description)

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
