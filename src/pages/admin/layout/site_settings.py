from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin

from ...app_routes import APP_ROUTES
from ...models import CMSPage, SiteSettings


def _build_homepage_choices():
    """Build grouped choices: App Routes + published CMS pages."""
    app_choices = [(r["url"], f"{r['title']} ({r['url']})") for r in APP_ROUTES]
    cms_choices = [
        (p["route"], f"{p['title']} ({p['route']})")
        for p in CMSPage.objects.filter(status="published").order_by("title").values("route", "title")
    ]
    choices = [("", "-- Select Homepage --")]
    if app_choices:
        choices.append(("App Routes", app_choices))
    if cms_choices:
        choices.append(("CMS Pages", cms_choices))
    return choices


class SiteSettingsForm(forms.ModelForm):
    homepage_route = forms.ChoiceField(
        required=False,
        help_text='Which page to render at "/". Select "/" (Home) for the default homepage.',
    )

    class Meta:
        model = SiteSettings
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["homepage_route"].choices = _build_homepage_choices()

    def clean_homepage_route(self):
        return (self.cleaned_data.get("homepage_route") or "/").strip()


@admin.register(SiteSettings)
class SiteSettingsAdmin(ModelAdmin):
    form = SiteSettingsForm
    list_display = ("__str__", "homepage_mode", "homepage_route_display")

    fieldsets = (
        (
            "Homepage",
            {
                "fields": ("homepage_route", "homepage_mode"),
                "description": (
                    "Choose which CMS page or app route visitors see at the root URL (/). "
                    "The homepage_mode controls event-related data prefetching (schedule, projects)."
                ),
            },
        ),
    )

    def homepage_route_display(self, obj):
        """Show the page title for the selected route."""
        route_map = {r["url"]: r["title"] for r in APP_ROUTES}
        # Also check CMS pages
        cms_page = CMSPage.objects.filter(route=obj.homepage_route, status="published").values("title").first()
        if cms_page:
            route_map[obj.homepage_route] = cms_page["title"]
        title = route_map.get(obj.homepage_route, obj.homepage_route)
        return f"{title} ({obj.homepage_route})"

    homepage_route_display.short_description = "Homepage"

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
