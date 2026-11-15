"""Type-to-confirm for admin add / change / delete: a submission is held (``pending``) until the admin types the
confirmation word on its confirmation page (``page``). Bulk actions: ``on_action``."""

import uuid
from urllib.parse import unquote

from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.contrib.admin.options import TO_FIELD_VAR
from django.core.exceptions import PermissionDenied
from django.forms.formsets import all_valid
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from .diff import compute_add_diff, compute_change_diff, compute_delete_diff, compute_formsets_diff
from .on_action import ConfirmActionMixin
from .page import ChangeConfirmationPageMixin
from .pending import PendingChangeMixin
from .post_data import serialize_post_data


class ConfirmOnSaveMixin(PendingChangeMixin, ChangeConfirmationPageMixin, ConfirmActionMixin):
    """Type-to-confirm for admin add / change / delete (bulk actions: ``ConfirmActionMixin``)."""

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
        ]
        return custom + super().get_urls()

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
        if add and not self.has_add_permission(request):
            raise PermissionDenied
        obj = None if add else self._change_target(request, object_id, to_field)
        if not add and obj is None:
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

        self._stash_pending_change(
            request,
            action_type=action_type,
            object_id=object_id,
            object_repr=object_repr,
            form_url=form_url,
            diff=diff,
        )
        confirm_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_confirm_change")
        return HttpResponseRedirect(confirm_url)

    def _change_target(self, request, object_id, to_field):
        """The object being changed (None if it is gone), after the change-permission check."""
        obj = self.get_object(request, unquote(object_id), to_field)
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        return obj

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
