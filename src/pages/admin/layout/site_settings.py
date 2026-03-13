from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin

from ...app_routes import APP_ROUTES
from ...models import SiteSettings

_ROUTE_CHOICES = [(r["url"], f'{r["title"]}  ({r["url"]})') for r in APP_ROUTES]


class SiteSettingsForm(forms.ModelForm):
    homepage_route = forms.ChoiceField(
        choices=_ROUTE_CHOICES,
        required=False,
        help_text='Which page to render at "/". Select "Home" to use the built-in homepage with mode variants.',
    )

    class Meta:
        model = SiteSettings
        fields = "__all__"


@admin.register(SiteSettings)
class SiteSettingsAdmin(ModelAdmin):
    form = SiteSettingsForm
    list_display = ("__str__", "homepage_mode", "homepage_route_display")

    fieldsets = (
        ("Homepage", {
            "fields": ("homepage_route", "homepage_mode"),
            "description": (
                "Choose which page visitors see at the root URL (/). "
                'When set to "Home", the homepage_mode controls which variant is shown.'
            ),
        }),
    )

    def homepage_route_display(self, obj):
        """Show the page title for the selected route."""
        route_map = {r["url"]: r["title"] for r in APP_ROUTES}
        title = route_map.get(obj.homepage_route, obj.homepage_route)
        if obj.homepage_route == "/":
            return f"Home (default)"
        return f"{title} ({obj.homepage_route})"

    homepage_route_display.short_description = "Homepage"

    def has_add_permission(self, request):
        # Only allow one instance
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
