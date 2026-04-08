from django import forms
from django.contrib import admin

from core.admin import BaseModelAdmin

from ...models import CMSPage, SiteSettings


class SiteSettingsForm(forms.ModelForm):
    homepage_page = forms.ModelChoiceField(
        queryset=CMSPage.objects.none(),
        required=False,
        empty_label="Use the published / page",
        help_text='Select the published CMS page to render at "/".',
    )

    class Meta:
        model = SiteSettings
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = CMSPage.objects.filter(status="published").order_by("title")

        current_page_id = getattr(self.instance, "homepage_page_id", None)
        if current_page_id:
            queryset = queryset | CMSPage.objects.filter(pk=current_page_id)

        self.fields["homepage_page"].queryset = queryset.distinct()
        # Match Unfold styling of other form controls (e.g., Title input)
        self.fields["homepage_page"].widget.attrs.update(
            {
                "class": (
                    "border border-base-200 bg-white font-medium min-w-20 "
                    "placeholder-base-400 rounded-default shadow-xs text-font-default-light text-sm "
                    "focus:outline-2 focus:-outline-offset-2 focus:outline-primary-600 "
                    "h-[38px] w-full max-w-2xl block"
                )
            }
        )

    def clean_homepage_page(self):
        page = self.cleaned_data.get("homepage_page")
        if page and page.status != "published":
            raise forms.ValidationError("Homepage must be a published CMS page.")
        return page


@admin.register(SiteSettings)
class SiteSettingsAdmin(BaseModelAdmin):
    form = SiteSettingsForm
    list_display = ("__str__", "homepage_page_display", "homepage_route_display")
    readonly_fields = ("homepage_route_display",)

    fieldsets = (
        (
            "Homepage",
            {
                "fields": ("homepage_page", "homepage_route_display"),
                "description": (
                    "Choose which published CMS page visitors see at the root URL (/). "
                    'If nothing is selected, the published "/" page is used as the fallback homepage.'
                ),
            },
        ),
    )

    def homepage_page_display(self, obj):
        page = CMSPage.objects.filter(pk=obj.homepage_page_id).first() if obj.homepage_page_id else None
        if not page:
            return "Fallback to /"
        return f"{page.title} ({page.route})"

    homepage_page_display.short_description = "Homepage Page"

    def homepage_route_display(self, obj):
        """Show the effective route visitors will see at /."""
        return obj.get_homepage_route()

    homepage_route_display.short_description = "Effective Homepage Route"

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        return False
