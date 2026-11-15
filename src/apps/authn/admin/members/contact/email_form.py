from django import forms
from django.utils.translation import gettext_lazy as _

from ....models import ContactEmail
from ..shared.help_texts import EMAIL_HELP_TEXTS, EMAIL_LABELS

PRIMARY_EMAIL_EDIT_ERROR = _(
    "The current primary email's owner, address, and type cannot be edited directly. "
    "Make another verified email primary first: “Switch primary email” on the member page, or the action "
    "“Make selected email primary” here."
)


PRIMARY_EMAIL_DELETE_ERROR = _(
    "The current primary email cannot be deleted directly. Make another email primary first."
)


PRIMARY_EMAIL_PROMOTION_ERROR = _(
    "A primary email cannot be assigned directly. Use the 'Make selected email primary' action, or “Switch primary "
    "email” on the member page."
)


def _primary_identity_changed(current, candidate) -> bool:
    """Return whether an update would rewrite the identity/type of a primary row."""
    return (
        current.member_id != candidate.member_id
        or current.email_address != candidate.email_address
        or current.email_type != candidate.email_type
    )


class ContactEmailAdminForm(forms.ModelForm):
    """Reject forged form submissions that bypass primary-email admin controls."""

    class Meta:
        model = ContactEmail
        fields = "__all__"
        labels = EMAIL_LABELS
        help_texts = EMAIL_HELP_TEXTS

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk:
            return cleaned_data

        current = ContactEmail.objects.filter(pk=self.instance.pk).first()
        if current is None or current.member_id is None:
            # An unowned row has no sign-in address to protect; let an admin adopt or fix it.
            return cleaned_data

        requested_member = cleaned_data.get("member", current.member)
        requested_email = cleaned_data.get("email_address", current.email_address)
        requested_type = cleaned_data.get("email_type", current.email_type)

        if current.email_type == "primary" and (
            requested_member != current.member
            or requested_email != current.email_address
            or requested_type != current.email_type
        ):
            raise forms.ValidationError(PRIMARY_EMAIL_EDIT_ERROR)

        if current.email_type != "primary" and requested_type == "primary":
            raise forms.ValidationError(PRIMARY_EMAIL_PROMOTION_ERROR)

        return cleaned_data
