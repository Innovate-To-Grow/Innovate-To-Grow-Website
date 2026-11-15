from django import forms

from apps.cms.models import CMSPage
from apps.cms.services.routing.route_redirects import page_route_conflicts


class CMSPageAdminForm(forms.ModelForm):
    keep_previous_url_as_redirect = forms.BooleanField(
        required=False,
        label="Keep previous URL as a permanent redirect",
        help_text=(
            "When this published page's route changes, create an active 301 mapping from the old route and "
            "retarget existing inbound mappings to the new route."
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["keep_previous_url_as_redirect"].initial = bool(
            self.instance.pk and self.instance.status == "published" and self.instance.route != "/"
        )

    def clean_route(self):
        route, conflicts = page_route_conflicts(
            self.cleaned_data.get("route"),
            exclude_page_id=self.instance.pk,
        )
        if conflicts:
            raise forms.ValidationError(conflicts[0].message)
        return route

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk or not cleaned_data.get("keep_previous_url_as_redirect"):
            return cleaned_data

        old_route = CMSPage.objects.filter(pk=self.instance.pk).values_list("route", flat=True).first()
        route_changed = old_route is not None and old_route != cleaned_data.get("route")
        if route_changed and old_route == "/":
            self.add_error(
                "keep_previous_url_as_redirect",
                "The site root cannot be a redirect source. Uncheck this option to rename the page.",
            )
        if route_changed and cleaned_data.get("status") != "published":
            self.add_error(
                "keep_previous_url_as_redirect",
                "The renamed destination must remain published to create an active redirect.",
            )
        return cleaned_data

    class Meta:
        model = CMSPage
        fields = "__all__"
        widgets = {
            "meta_description": forms.TextInput(
                attrs={
                    "class": (
                        "border border-base-200 bg-white font-medium min-w-20 "
                        "placeholder-base-400 rounded-default shadow-xs text-font-default-light text-sm "
                        "focus:outline-2 focus:-outline-offset-2 focus:outline-primary-600 "
                        "h-[38px] w-full max-w-2xl block"
                    )
                }
            ),
            "route": forms.TextInput(
                attrs={"data-role": "cms-route-source", "autocomplete": "off", "spellcheck": "false"}
            ),
        }
