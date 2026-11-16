"""The confirmation plumbing every type-to-confirm flow shares (bulk actions and add / change / delete)."""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse


class ConfirmationBaseMixin:
    require_confirmation = True

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
