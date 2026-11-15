"""The review step of a registration sheet sync: the signed token a review page carries, and its confirmation."""

from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.shortcuts import redirect

from apps.event.services import registration_sheet_sync as sync_api

from .form import configuration_fingerprint

REVIEW_SALT = "event.registration-sheet-sync.review"
REVIEW_MAX_AGE = 600


class SheetSyncReviewMixin:
    """The review helpers of ``RegistrationSheetSyncAdminMixin``."""

    @staticmethod
    def _sheet_sync_review(request, event, config, preview, operation):
        return {
            "operation": operation,
            "token": signing.dumps(
                {
                    "event": str(event.pk),
                    "user": str(request.user.pk),
                    "operation": operation,
                    "config": configuration_fingerprint(event, config),
                    "fingerprint": preview["fingerprint"],
                },
                salt=REVIEW_SALT,
            ),
        }

    def _confirm_sheet_sync_review(self, request, event, config, operation):
        if request.POST.get("backup_acknowledged") != "on":
            raise ValidationError("Confirm that a backup will be created before continuing.")
        try:
            review = signing.loads(request.POST.get("review_token", ""), salt=REVIEW_SALT, max_age=REVIEW_MAX_AGE)
        except signing.BadSignature as exc:
            raise ValidationError("This review is missing or expired. Preview the operation again.") from exc
        expected = {
            "event": str(event.pk),
            "user": str(request.user.pk),
            "operation": operation,
            "config": configuration_fingerprint(event, config),
        }
        if any(review.get(key) != value for key, value in expected.items()):
            raise ValidationError("The saved settings or review have changed. Preview the operation again.")
        if operation == "adoption":
            count = sync_api.sync_registrations_to_sheet(
                event, adopt_legacy=True, expected_fingerprint=review["fingerprint"]
            )
            messages.success(request, f"Legacy rows migrated after backup. {count} managed row changes applied.")
        else:
            sync_api.create_registration_worksheet(event, expected_fingerprint=review["fingerprint"])
            messages.success(
                request, "Backup completed and a new managed worksheet created. The previous worksheet was preserved."
            )
        self.log_change(
            request, event, f"Completed registration sheet {operation} after preview and backup confirmation."
        )
        return redirect("admin:event_event_sheet_sync", event.pk)
