"""Site Settings: one field per design token, custom CSS revisions and the CodeMirror editor."""

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.authn.models import Member
from apps.cms.admin.layout.custom_css_revision import CustomCssRevisionAdmin
from apps.cms.admin.layout.site_settings import SiteSettingsAdmin, SiteSettingsForm
from apps.cms.admin.layout.site_settings_tokens import reset_field_name, token_field_name, unknown_tokens
from apps.cms.models import CustomCssRevision, SiteSettings
from apps.cms.models.content.layout.site_settings import default_design_tokens
from apps.cms.services.styles.revisions import KEEP_REVISIONS, record_custom_css, restore_custom_css


def token_data(**overrides):
    """Form data with every token field at its default, plus ``overrides`` by field name."""
    data = {
        token_field_name(group, key): value
        for group, values in default_design_tokens().items()
        for key, value in values.items()
    }
    data.update(overrides)
    return data


class DesignTokenFieldsTests(TestCase):
    def setUp(self):
        self.settings = SiteSettings.load()

    def test_every_default_token_has_a_field_showing_the_stored_value(self):
        self.settings.design_tokens["colors"]["primary"] = "#123456"
        self.settings.save()

        form = SiteSettingsForm(instance=self.settings)

        for group, values in default_design_tokens().items():
            for key in values:
                self.assertIn(token_field_name(group, key), form.fields)
            self.assertIn(reset_field_name(group), form.fields)
        self.assertEqual(form.fields[token_field_name("colors", "primary")].initial, "#123456")
        self.assertEqual(form.fields[token_field_name("colors", "primary")].label, "--itg-color-primary")
        self.assertNotIn("design_tokens", form.fields)

    def test_hex_colours_get_a_colour_picker_unless_the_stored_value_is_not_hex(self):
        self.settings.design_tokens["colors"]["secondary"] = "rgb(0 84 135)"
        self.settings.save()

        form = SiteSettingsForm(instance=self.settings)

        self.assertEqual(form.fields[token_field_name("colors", "primary")].widget.input_type, "color")
        self.assertEqual(form.fields[token_field_name("colors", "secondary")].widget.attrs.get("type"), None)
        self.assertNotEqual(form.fields[token_field_name("typography", "font_size_h1")].widget.input_type, "color")

    def test_saving_folds_the_fields_back_into_the_token_json(self):
        data = token_data(
            **{token_field_name("colors", "primary"): "#8a1c1c", token_field_name("layout", "page_gutter"): "2rem"}
        )
        form = SiteSettingsForm(instance=self.settings, data=data)

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.settings.refresh_from_db()
        self.assertEqual(self.settings.design_tokens["colors"]["primary"], "#8a1c1c")
        self.assertEqual(self.settings.design_tokens["layout"]["page_gutter"], "2rem")

    def test_an_unsafe_value_is_refused_on_its_field(self):
        name = token_field_name("colors", "primary")
        form = SiteSettingsForm(instance=self.settings, data=token_data(**{name: "red; } body { display: none"}))

        self.assertFalse(form.is_valid())
        self.assertIn(name, form.errors)

    def test_a_blank_field_means_the_default(self):
        self.settings.design_tokens["colors"]["primary"] = "#123456"
        self.settings.save()
        form = SiteSettingsForm(instance=self.settings, data=token_data(**{token_field_name("colors", "primary"): " "}))

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.settings.refresh_from_db()
        self.assertEqual(self.settings.design_tokens["colors"]["primary"], default_design_tokens()["colors"]["primary"])

    def test_reset_puts_back_the_whole_group(self):
        data = token_data(**{token_field_name("layout", "page_gutter"): "9rem", reset_field_name("layout"): "on"})
        form = SiteSettingsForm(instance=self.settings, data=data)

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.settings.refresh_from_db()
        self.assertEqual(self.settings.design_tokens["layout"], default_design_tokens()["layout"])

    def test_tokens_without_a_field_are_kept(self):
        self.settings.design_tokens["colors"]["brand_extra"] = "#abcdef"
        self.settings.design_tokens["custom_group"] = {"x": "1px"}
        self.settings.save()

        form = SiteSettingsForm(instance=self.settings, data=token_data())
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.settings.refresh_from_db()
        self.assertEqual(self.settings.design_tokens["colors"]["brand_extra"], "#abcdef")
        self.assertEqual(self.settings.design_tokens["custom_group"], {"x": "1px"})
        self.assertEqual(
            unknown_tokens(self.settings.design_tokens),
            {"colors": {"brand_extra": "#abcdef"}, "custom_group": {"x": "1px"}},
        )


class CustomCssRevisionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = Member.objects.create_superuser(password="testpass123", first_name="Theme", last_name="Admin")
        self.client.force_login(self.admin)
        self.settings = SiteSettings.load()

    def test_keeps_only_the_newest_revisions(self):
        for index in range(KEEP_REVISIONS + 3):
            self.settings.custom_css = f".r{index} {{ color: red; }}"
            record_custom_css(self.settings, self.admin)

        revisions = list(CustomCssRevision.objects.all())
        self.assertEqual(len(revisions), KEEP_REVISIONS)
        self.assertEqual(revisions[0].css, f".r{KEEP_REVISIONS + 2} {{ color: red; }}")
        self.assertEqual(revisions[0].created_by, self.admin)

    def test_restore_makes_a_revision_live_again_and_records_it(self):
        self.settings.custom_css = ".old { color: red; }"
        record_custom_css(self.settings)
        old = CustomCssRevision.objects.get()
        self.settings.custom_css = ".new { color: blue; }"
        self.settings.save()

        restore_custom_css(old, self.admin)

        self.assertEqual(SiteSettings.load().custom_css, ".old { color: red; }")
        self.assertEqual(CustomCssRevision.objects.count(), 2)
        self.assertEqual(CustomCssRevision.objects.first().created_by, self.admin)

    def _request(self):
        request = RequestFactory().post("/admin/")
        request.user = self.admin
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_saving_site_settings_records_a_revision_only_when_the_css_changes(self):
        model_admin = SiteSettingsAdmin(SiteSettings, AdminSite())
        for css in (".site-header { color: red; }", ".site-header { color: red; }"):
            settings = SiteSettings.load()
            form = SiteSettingsForm(instance=settings, data=token_data(custom_css=css))
            self.assertTrue(form.is_valid(), form.errors)
            model_admin.save_model(self._request(), form.save(commit=False), form, change=True)

        self.assertEqual(SiteSettings.load().custom_css, ".site-header { color: red; }")
        revisions = list(CustomCssRevision.objects.all())
        self.assertEqual([revision.css for revision in revisions], [".site-header { color: red; }"])
        self.assertEqual(revisions[0].created_by, self.admin)

    def test_the_restore_action_needs_exactly_one_revision(self):
        for css in (".a {}", ".b {}"):
            self.settings.custom_css = css
            self.settings.save()
            record_custom_css(self.settings)
        model_admin = CustomCssRevisionAdmin(CustomCssRevision, AdminSite())
        oldest = CustomCssRevision.objects.last()

        model_admin.restore_revision(self._request(), CustomCssRevision.objects.all())
        self.assertEqual(SiteSettings.load().custom_css, ".b {}")

        model_admin.restore_revision(self._request(), CustomCssRevision.objects.filter(pk=oldest.pk))
        self.assertEqual(SiteSettings.load().custom_css, ".a {}")
        self.assertEqual(CustomCssRevision.objects.first().css, ".a {}")

    def test_the_change_page_loads_the_css_editor_and_links_the_revisions(self):
        response = self.client.get(reverse("admin:cms_sitesettings_change", args=[self.settings.pk]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("vendor/codemirror/5.65.16/mode/css/css.min.js", content)
        self.assertIn("cms/js/custom-css-editor.js", content)
        self.assertIn(reverse("admin:cms_customcssrevision_changelist"), content)
        self.assertIn("Design tokens: Colors", content)
        self.assertIn('type="color"', content)
