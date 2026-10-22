import json

from django import forms
from django.contrib import admin
from django.core.cache import cache
from django.urls import reverse
from django.utils.html import format_html

from apps.cms.services.styles.custom_css import custom_css_errors
from apps.cms.services.styles.revisions import record_custom_css
from apps.core.admin import BaseModelAdmin

from ...models import CMSPage, SiteSettings
from .site_settings_tokens import DesignTokenFormMixin, token_fieldsets, token_form_fields, unknown_tokens


class SiteSettingsBaseForm(DesignTokenFormMixin, forms.ModelForm):
    homepage_page = forms.ModelChoiceField(
        queryset=CMSPage.objects.none(),
        required=False,
        empty_label="Use the published / page",
        help_text='Select the published CMS page to render at "/".',
    )

    class Meta:
        model = SiteSettings
        # design_tokens is edited through one field per token (site_settings_tokens.py), folded back in clean().
        fields = ("homepage_page", "custom_css")
        widgets = {
            "custom_css": forms.Textarea(attrs={"rows": 18, "spellcheck": "false", "class": "font-mono"}),
        }

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
        self.init_token_fields()

    def clean_custom_css(self):
        css = self.cleaned_data.get("custom_css") or ""
        errors = custom_css_errors(css)
        if errors:
            raise forms.ValidationError(errors)
        return css

    def clean_homepage_page(self):
        page = self.cleaned_data.get("homepage_page")
        if page and page.status != "published":
            raise forms.ValidationError("Homepage must be a published CMS page.")
        return page

    def clean(self):
        cleaned_data = super().clean()
        self.instance.design_tokens = self.tokens_from_cleaned_data()
        return cleaned_data


# The token fields are declared, not added in __init__: the admin builds its form class from the
# fieldsets, and a field the class does not declare is an error there.
SiteSettingsForm = type("SiteSettingsForm", (SiteSettingsBaseForm,), token_form_fields())


@admin.register(SiteSettings)
class SiteSettingsAdmin(BaseModelAdmin):
    form = SiteSettingsForm
    change_form_template = "admin/cms/sitesettings/change_form.html"
    list_display = ("__str__", "homepage_page_display", "homepage_route_display")
    readonly_fields = ("homepage_route_display", "other_design_tokens")

    homepage_fieldset = (
        "Homepage",
        {
            "fields": ("homepage_page", "homepage_route_display"),
            "description": (
                "Choose which published CMS page visitors see at the root URL (/). "
                'If nothing is selected, the published "/" page is used as the fallback homepage.'
            ),
        },
    )
    custom_css_fieldset = (
        "Custom CSS",
        {
            "fields": ("custom_css",),
            "description": (
                "Site-wide CSS added after every bundled stylesheet; see docs/cms-admin/theme-and-custom-css.md. "
                "Saving checks it for unbalanced braces and forbidden constructs (@import, expression(), "
                "javascript: URLs) and keeps a revision you can restore. For lasting changes, prefer a change "
                "to the CSS in the repository."
            ),
        },
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = [self.homepage_fieldset, *token_fieldsets()]
        if obj is not None and unknown_tokens(obj.design_tokens):
            fieldsets.append(("Other design tokens", {"fields": ("other_design_tokens",)}))
        fieldsets.append(self.custom_css_fieldset)
        return fieldsets

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

    def other_design_tokens(self, obj):
        """Stored tokens without a field here: kept on save, served when their keys are valid."""
        extra = unknown_tokens(obj.design_tokens) if obj else {}
        return format_html("<pre>{}</pre>", json.dumps(extra, indent=2, ensure_ascii=False)) if extra else "-"

    other_design_tokens.short_description = "Kept as stored"

    def render_change_form(self, request, context, *args, **kwargs):
        context["custom_css_revisions_url"] = reverse("admin:cms_customcssrevision_changelist")
        return super().render_change_form(request, context, *args, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        cache.delete("layout:data")
        if form is not None and "custom_css" in form.changed_data:
            record_custom_css(obj, request.user)

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_add_permission(self, request):
        return super().has_add_permission(request) and not SiteSettings.objects.exists()

    # noinspection PyUnusedLocal,PyMethodMayBeStatic
    def has_delete_permission(self, request, obj=None):
        return False
