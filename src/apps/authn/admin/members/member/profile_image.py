from django import forms
from django.core.exceptions import ValidationError

from ....services.members.accounts.profile_image import ProfileImageError, encode_profile_image


class Base64ImageWidget(forms.ClearableFileInput):
    """File upload widget for the base64 ``data:`` URI stored in ``Member.profile_image``.

    The preview is rendered from ``preview_url`` (an admin view that streams the decoded bytes), never
    by inlining the stored string. Inlining it put the whole value — up to ~6.8 MB — into one
    ``<img src>`` in the middle of the "Personal Info" fieldset, so on a slow or truncated response
    everything after it (the remaining fieldsets, both contact inlines and the only Save button) never
    arrived and the page looked read-only. The rendered markup is now a constant size for every member.
    """

    template_name = "admin/authn/member/base64_image.html"
    # i2g-admin-file-input: see admin/css/file-input.css (WebKit file button styling).
    _file_classes = "i2g-admin-file-input block w-full text-sm text-font-default-light dark:text-font-default-dark"

    def __init__(self, attrs=None):
        defaults = {"class": self._file_classes}
        if attrs:
            defaults.update(attrs)
        super().__init__(attrs=defaults)
        # Set per bound form by MemberChangeForm.__init__; the widget is deep-copied with the field,
        # so this stays request-scoped.
        self.preview_url = ""

    def value_from_datadict(self, data, files, name):
        """Return the upload, ``""`` to clear, or ``None`` for "keep the current image".

        The upload object is returned as-is rather than base64-encoded here: encoding needs to raise
        ``ValidationError`` (see ``Base64ImageField.to_python``), and reading the stream in a widget
        breaks any later reader. ``ConfirmOnSaveMixin`` caches ``request.FILES`` *after* the form has
        validated, so a widget that consumed the stream made it cache zero bytes and the confirmed
        save then overwrote the member's real image with an empty ``data:`` URI.
        """
        upload = files.get(name)
        if upload:
            return upload
        if self.clear_checkbox_name(name) in data:
            return ""
        return None  # No change

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def format_value(self, value):
        # Never let the stored base64 string reach the template context.
        return None

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        has_image = bool(value) and isinstance(value, str)
        context["widget"].update(
            {
                "value": None,
                "is_initial": has_image,
                "preview_url": self.preview_url if has_image else "",
            }
        )
        return context


class Base64ImageField(forms.CharField):
    """Form field for the base64 ``data:`` URI stored in ``Member.profile_image``.

    ``profile_image`` is a ``TextField``, so ``fields = "__all__"`` would give it a plain ``CharField``
    whose ``has_changed`` coerces the widget's "no change" ``None`` to ``""`` — making
    ``"data:image/png;base64,…" != ""`` true on every save. Every member save therefore logged
    "Changed Profile Image" and produced a phantom confirm-on-save diff row. ``FileField.has_changed``
    has the rule this needs (``data is not None``); mirror it here, and do the validation/encoding in
    ``to_python`` where a ``ValidationError`` can reach the user.
    """

    widget = Base64ImageWidget

    def to_python(self, value):
        if value is None or value == "":
            return value
        if hasattr(value, "read"):
            try:
                return encode_profile_image(value)
            except ProfileImageError as exc:
                raise ValidationError(str(exc), code="invalid_image") from exc
        # Already-encoded string (programmatic use and existing tests).
        return super().to_python(value)

    def has_changed(self, initial, data):
        if data is None:
            return False  # No file chosen and the clear checkbox was not ticked.
        if data == "":
            return bool(initial)  # Clearing only changes anything if there was an image.
        return True  # A file was chosen.
