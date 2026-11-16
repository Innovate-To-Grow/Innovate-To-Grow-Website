from django import forms
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget, UnfoldAdminTextInputWidget

from apps.cms.models import RouteRedirect
from apps.cms.services.routing.route_redirects import destination_route_choices


class RouteRedirectAdminForm(forms.ModelForm):
    destination_path = forms.ChoiceField(
        label="Destination path",
        help_text="Choose a published CMS page or fixed public application route.",
        widget=UnfoldAdminSelectWidget,
    )

    class Meta:
        model = RouteRedirect
        fields = "__all__"
        widgets = {
            "source_path": UnfoldAdminTextInputWidget(
                attrs={
                    "data-role": "route-redirect-source",
                    "autocomplete": "off",
                    "spellcheck": "false",
                }
            ),
            "notes": UnfoldAdminTextareaWidget(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "Select a destination…"), *destination_route_choices()]
        current_destination = self.instance.destination_path if self.instance.pk else ""
        flattened_values = {value for group in choices[1:] for value, _label in group[1]}
        if current_destination and current_destination not in flattened_values:
            choices.append(("Current value", [(current_destination, f"{current_destination} (currently unavailable)")]))
        self.fields["destination_path"].choices = choices
