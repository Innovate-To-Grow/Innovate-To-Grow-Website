from django.test import SimpleTestCase

from apps.system_intelligence.admin.actions.rendering import (
    _heading_level,
    _link_label,
    _render_block_body,
    _render_faq_list,
    _render_heading_and_html,
    _render_link_list,
    _render_preview_block,
    _render_preview_blocks,
    _render_section_group,
    _render_table,
    _safe_href,
)


class RenderPreviewBlockTests(SimpleTestCase):
    def test_non_dict_block_renders_empty_string(self):
        self.assertEqual(_render_preview_block("not-a-dict"), "")
        self.assertEqual(_render_preview_block(None), "")

    def test_block_with_no_previewable_body_renders_empty_message(self):
        # An unknown block type with empty data has no heading/body, so the
        # empty-content fallback (line 25) is rendered.
        html = _render_preview_block({"block_type": "mystery", "data": {}})
        self.assertIn("No previewable content for this block.", html)
        self.assertIn("si-action-preview-block--mystery", html)
        self.assertIn("Mystery", html)

    def test_block_uses_admin_label_and_renders_body(self):
        html = _render_preview_block(
            {
                "block_type": "rich_text",
                "admin_label": "Hero Section",
                "data": {"heading": "Welcome", "body_html": "<p>Hi</p>"},
            }
        )
        self.assertIn("Hero Section", html)
        self.assertIn("<h2>Welcome</h2>", html)

    def test_block_with_non_dict_data_falls_back_to_empty_data(self):
        html = _render_preview_block({"block_type": "rich_text", "data": "oops"})
        self.assertIn("No previewable content", html)

    def test_render_preview_blocks_joins_each_block(self):
        html = _render_preview_blocks(
            [
                {"block_type": "rich_text", "data": {"heading": "A", "body_html": "<p>x</p>"}},
                {"block_type": "rich_text", "data": {"heading": "B", "body_html": "<p>y</p>"}},
            ]
        )
        self.assertIn("<h2>A</h2>", html)
        self.assertIn("<h2>B</h2>", html)


class RenderBlockBodyDispatchTests(SimpleTestCase):
    def test_image_text_uses_heading_and_html_renderer(self):
        html = _render_block_body("image_text", {"heading": "Pic", "body_html": "<p>caption</p>"})
        self.assertIn("<h2>Pic</h2>", html)
        self.assertIn('class="cms-image-text"', html)

    def test_link_list_dispatch(self):
        html = _render_block_body("link_list", {"items": [{"url": "/a", "title": "A"}]})
        self.assertIn('class="cms-link-list-items"', html)
        self.assertIn(">A</a>", html)

    def test_table_dispatch(self):
        html = _render_block_body("table", {"rows": [["c1", "c2"]]})
        self.assertIn('class="cms-table"', html)
        self.assertIn("<td>c1</td>", html)

    def test_default_block_type_uses_dynamic_css_class(self):
        html = _render_block_body("custom_kind", {"heading": "H", "body_html": "<p>b</p>"})
        self.assertIn('class="cms-custom-kind"', html)
        self.assertIn("<h2>H</h2>", html)


class RenderSectionGroupTests(SimpleTestCase):
    def test_non_list_sections_falls_back_to_heading_renderer(self):
        html = _render_section_group({"heading": "Group", "body_html": "<p>body</p>"})
        self.assertIn('class="cms-section-group"', html)
        self.assertIn("<h2>Group</h2>", html)

    def test_list_sections_renders_each_section(self):
        html = _render_section_group(
            {"sections": [{"heading": "S1", "body_html": "<p>one</p>", "heading_level": 3}, "skip-me"]}
        )
        self.assertIn("<h3>S1</h3>", html)
        self.assertIn("one", html)


class RenderFaqListTests(SimpleTestCase):
    def test_non_list_faqs_falls_back_to_heading_renderer(self):
        html = _render_faq_list({"heading": "FAQs", "body_html": "<p>body</p>"})
        self.assertIn('class="cms-faq-list"', html)
        self.assertIn("<h2>FAQs</h2>", html)

    def test_list_faqs_renders_question_and_answer(self):
        html = _render_faq_list({"items": [{"question": "Q?", "answer": "<p>A</p>"}]})
        self.assertIn("<h3>Q?</h3>", html)
        self.assertIn("A", html)


class RenderLinkListTests(SimpleTestCase):
    def test_non_list_items_falls_back_to_heading_renderer(self):
        html = _render_link_list({"heading": "Links", "body_html": "<p>body</p>"})
        self.assertIn('class="cms-link-list"', html)

    def test_list_items_renders_anchors_with_descriptions(self):
        html = _render_link_list({"items": [{"url": "https://example.com", "title": "Example", "description": "site"}]})
        self.assertIn('href="https://example.com"', html)
        self.assertIn("Example", html)
        self.assertIn("- site", html)


class RenderTableTests(SimpleTestCase):
    def test_non_list_rows_falls_back_to_heading_renderer(self):
        html = _render_table({"heading": "Table", "body_html": "<p>body</p>"})
        self.assertIn('class="cms-table"', html)

    def test_list_rows_renders_cells_and_escapes_content(self):
        html = _render_table({"rows": [["<b>bold</b>", "plain"], "not-a-row"]})
        self.assertIn("<tr>", html)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", html)
        self.assertIn("<td>plain</td>", html)


class RenderHeadingAndHtmlTests(SimpleTestCase):
    def test_renders_heading_then_body(self):
        html = _render_heading_and_html({"heading": "T", "heading_level": 4, "body_html": "<p>x</p>"}, "css")
        self.assertIn("<h4>T</h4>", html)
        self.assertIn('class="css"', html)

    def test_returns_empty_when_no_heading_or_body(self):
        self.assertEqual(_render_heading_and_html({}, "css"), "")


class SafeHrefTests(SimpleTestCase):
    def test_non_string_returns_hash(self):
        self.assertEqual(_safe_href(123), "#")

    def test_control_chars_stripped_then_blank_returns_hash(self):
        self.assertEqual(_safe_href("\x00\x01"), "#")

    def test_scheme_relative_returns_hash(self):
        self.assertEqual(_safe_href("//attacker.example"), "#")
        self.assertEqual(_safe_href("\\\\attacker"), "#")

    def test_disallowed_scheme_returns_hash(self):
        self.assertEqual(_safe_href("javascript:alert(1)"), "#")
        self.assertEqual(_safe_href("ftp://host/file"), "#")

    def test_valid_http_and_relative_urls_preserved(self):
        self.assertEqual(_safe_href("https://example.com/page"), "https://example.com/page")
        self.assertEqual(_safe_href("/about"), "/about")
        self.assertEqual(_safe_href("#section"), "#section")


class LinkLabelTests(SimpleTestCase):
    def test_uses_title_when_present(self):
        self.assertEqual(_link_label({"title": "My Title", "url": "/x"}), "My Title")

    def test_falls_back_to_label(self):
        self.assertEqual(_link_label({"label": "My Label"}), "My Label")

    def test_uses_url_when_safe_and_no_title(self):
        self.assertEqual(_link_label({"url": "https://example.com"}), "https://example.com")

    def test_uses_generic_link_when_url_unsafe(self):
        self.assertEqual(_link_label({"url": "javascript:evil()"}), "Link")


class HeadingLevelTests(SimpleTestCase):
    def test_clamps_within_range(self):
        # 0 is falsy so `value or default` selects the default of 2.
        self.assertEqual(_heading_level(0, default=2), 2)
        self.assertEqual(_heading_level(-5, default=2), 1)
        self.assertEqual(_heading_level(9, default=2), 6)
        self.assertEqual(_heading_level(3, default=2), 3)

    def test_invalid_value_uses_default(self):
        self.assertEqual(_heading_level("not-an-int", default=4), 4)
        self.assertEqual(_heading_level(None, default=5), 5)
