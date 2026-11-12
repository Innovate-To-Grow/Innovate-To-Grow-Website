"""Forms of the member import: the upload, the review's posted choices, and the confirmation."""

from django import forms

from apps.authn.models import MemberImportBatch

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_INPUT_CLASSES = (
    "w-full border border-base-200 dark:border-base-700 bg-white dark:bg-base-900"
    " text-font-default-light dark:text-font-default-dark rounded-default px-3 py-2 text-sm"
)
_FILE_CLASSES = "i2g-admin-file-input block w-full text-sm text-font-default-light dark:text-font-default-dark"


class MemberImportForm(forms.Form):
    """Step 1: the file, the default password for new members, and what rows matching a member do by default."""

    excel_file = forms.FileField(
        label="Excel File",
        help_text="Upload an Excel workbook in .xlsx format",
        widget=forms.FileInput(attrs={"accept": ".xlsx", "class": _FILE_CLASSES}),
    )
    set_password = forms.CharField(
        label="Default Password",
        required=False,
        help_text="Set a default password for imported users (leave empty to generate random passwords)",
        widget=forms.PasswordInput(attrs={"class": _INPUT_CLASSES, "autocomplete": "new-password"}),
    )
    mode = forms.ChoiceField(
        label="Rows that match an existing member",
        choices=MemberImportBatch.Mode.choices,
        initial=MemberImportBatch.Mode.UPDATE_EXISTING,
        widget=forms.RadioSelect,
        help_text=(
            "The default for a row whose Primary Email (or Member UUID) is an existing member's. Every other case is "
            "decided on the review page, and nothing is written before you confirm."
        ),
    )
    upload_anyway = forms.BooleanField(
        label="This file was uploaded before; review it again anyway",
        required=False,
        widget=forms.CheckboxInput,
    )

    def __init__(self, *args, can_update: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.can_update = can_update
        if not can_update:
            self.fields["mode"].initial = MemberImportBatch.Mode.SKIP_EXISTING
            self.fields[
                "mode"
            ].help_text += " You do not have permission to change members, so rows that match one are skipped."

    def clean_excel_file(self):
        file = self.cleaned_data.get("excel_file")
        if file:
            # openpyxl reads only the .xlsx format; an old .xls workbook used to fail later with a bare
            # "Error creating members".
            if not file.name.lower().endswith(".xlsx"):
                raise forms.ValidationError(
                    "Please upload an .xlsx file. Older .xls workbooks can't be read: save the file as .xlsx first."
                )
            if file.size > MAX_UPLOAD_BYTES:
                raise forms.ValidationError("File size cannot exceed 5MB")
        return file

    def clean_mode(self):
        mode = self.cleaned_data["mode"]
        if mode == MemberImportBatch.Mode.UPDATE_EXISTING and not self.can_update:
            raise forms.ValidationError("You do not have permission to update existing members.")
        return mode


class ImportConfirmForm(forms.Form):
    """Step 3: the typed confirmation and the version of the choices the summary showed."""

    confirmation_text = forms.CharField(required=False)
    version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def __init__(self, *args, require_text: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_text = require_text

    def clean_confirmation_text(self):
        text = self.cleaned_data.get("confirmation_text", "").strip()
        if self.require_text and text.lower() != "import":
            raise forms.ValidationError('Type "import" to confirm.')
        return text


def parse_review_post(data, row_numbers) -> tuple[dict, str, dict, int | None]:
    """``(posted choices, command, bulk selections, version)`` from the review form.

    Every submit button posts every selection on the page, so nothing is lost when a bulk button is pressed. A row's
    choice is its radio (``choice-<row>``), or for a ready row its default unless ``skip-<row>`` is ticked. Its ticks
    are the ``tick-<row>`` checkboxes, read only when the page rendered them (marker ``ticks-<row>``): an unticked box
    posts nothing. ``None`` means "not on the form": the stored value stays. The command is the pressed button's
    ``action`` value.
    """
    posted = {}
    for number in row_numbers:
        choice = data.get(f"choice-{number}")
        if choice is None and f"ready-{number}" in data:
            choice = "skip" if data.get(f"skip-{number}") else data.get(f"ready-{number}")
        ticks = data.getlist(f"tick-{number}") if f"ticks-{number}" in data else None
        if choice is not None or ticks is not None:
            posted[number] = (choice, ticks)
    bulk = {key.removeprefix("bulk-"): value for key, value in data.items() if key.startswith("bulk-")}
    try:
        version = int(data.get("version", ""))
    except ValueError:
        version = None
    return posted, data.get("action", "save"), bulk, version
