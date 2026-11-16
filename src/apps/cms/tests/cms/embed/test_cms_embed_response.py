from apps.cms.tests.cms.embed.test_cms_embed import _EmbedBlockViewCase


class EmbedBlockViewTest(_EmbedBlockViewCase):
    def test_response_includes_expected_top_level_keys(self):
        response = self.client.get("/cms/embed/contact-widget/")
        data = response.json()
        self.assertEqual(
            set(data.keys()),
            {
                "widget_type",
                "app_route",
                "blocks",
                "page_css_class",
                "hidden_sections",
                "hide_section_titles",
            },
        )

    def test_blocks_widget_reports_widget_type(self):
        response = self.client.get("/cms/embed/contact-widget/")
        data = response.json()
        self.assertEqual(data["widget_type"], "blocks")
        self.assertEqual(data["app_route"], "")

    def test_hide_section_titles_defaults_to_false(self):
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertFalse(response.json()["hide_section_titles"])
        self.assertEqual(response.json()["hidden_sections"], [])

    def test_hide_section_titles_reflects_widget_setting(self):
        self.widget.hide_section_titles = True
        self.widget.save(update_fields=["hide_section_titles"])
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertTrue(response.json()["hide_section_titles"])
        self.assertEqual(response.json()["hidden_sections"], ["section_titles"])

    def test_hidden_sections_reflect_widget_setting(self):
        self.widget.hidden_sections = ["section_titles"]
        self.widget.save(update_fields=["hidden_sections"])
        response = self.client.get("/cms/embed/contact-widget/")
        self.assertEqual(response.json()["hidden_sections"], ["section_titles"])
        self.assertTrue(response.json()["hide_section_titles"])
