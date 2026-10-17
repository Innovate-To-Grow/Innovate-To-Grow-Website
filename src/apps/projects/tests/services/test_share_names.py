from django.test import SimpleTestCase

from apps.projects.services.share_names import DEFAULT_NAME_MAX_CHARS, DEFAULT_SHARE_NAME, default_share_name

PROJECT_SUMMARY_BLOCK = (
    '<div data-past-project-note-curation="project-summary">'
    '<div data-past-project-key="k1"><div><strong>Project 1</strong></div>'
    "<div><strong>Year-Semester:</strong> 2026 Spring</div>"
    "<div><strong>Project Title:</strong> Upgrading Advanced Image Analysis Platform</div></div>"
    "<div>------------------------------</div>"
    '<div data-past-project-key="k2"><div><strong>Project 2</strong></div></div>'
    "</div>"
)


class DefaultShareNameTests(SimpleTestCase):
    def test_empty_or_blank_notes_use_the_generic_title(self):
        for note in ["", "<br>", "<div>&nbsp;</div>", "<div> </div><p></p>", None]:
            with self.subTest(note=note):
                self.assertEqual(default_share_name(note), DEFAULT_SHARE_NAME)

    def test_inserted_project_details_never_name_the_curation(self):
        self.assertEqual(default_share_name(PROJECT_SUMMARY_BLOCK), DEFAULT_SHARE_NAME)

    def test_owner_text_before_inserted_projects_is_used(self):
        self.assertEqual(default_share_name("<div>Hi Bob,</div><br><br>" + PROJECT_SUMMARY_BLOCK), "Hi Bob,")
        self.assertEqual(default_share_name("Western Digital picks" + PROJECT_SUMMARY_BLOCK), "Western Digital picks")

    def test_uses_only_the_first_line(self):
        self.assertEqual(
            default_share_name("<div>Spring 2026 finalists</div><div>Please review by Friday</div>"),
            "Spring 2026 finalists",
        )
        self.assertEqual(default_share_name("First line<br>second line"), "First line")

    def test_skips_separator_lines_and_flattens_emphasis(self):
        self.assertEqual(default_share_name("<div>------</div><div>Real title</div>"), "Real title")
        self.assertEqual(default_share_name("<div><b>Spring 2026</b>  <i>finalists</i></div>"), "Spring 2026 finalists")

    def test_splits_lines_the_way_browsers_write_them(self):
        # Chromium/WebKit keep the first typed line as a bare text node and wrap later lines in <div>.
        self.assertEqual(
            default_share_name("Spring 2026 finalists<div>Please review by Friday</div>"), "Spring 2026 finalists"
        )
        # bleach strips non-allowlisted blocks (h1, li) and leaves their text beside the next <div>.
        self.assertEqual(default_share_name("Title<div>body</div>"), "Title")
        self.assertEqual(default_share_name("Pasted first line\nsecond"), "Pasted first line")

    def test_keeps_a_heading_typed_inside_the_inserted_block(self):
        note = PROJECT_SUMMARY_BLOCK.replace(
            '<div data-past-project-key="k1">',
            '<div data-past-project-key="k1"><div><strong>My CSE list</strong></div>',
        )
        self.assertEqual(default_share_name(note), "My CSE list")

    def test_skips_inserted_details_once_formatting_was_cleared(self):
        flattened = (
            "Project 1<br>Year-Semester: 2026 Spring<br>Project Title: Upgrading Advanced Image Analysis Platform"
            "<br>------------------------------<br>Project 2"
        )
        self.assertEqual(default_share_name(flattened), DEFAULT_SHARE_NAME)

    def test_skips_every_line_of_a_multi_line_inserted_abstract(self):
        note = (
            '<div data-past-project-note-curation="project-summary"><div data-past-project-key="k1">'
            "<div><strong>Abstract:</strong> Line one.\nLine two.</div></div></div>"
        )
        self.assertEqual(default_share_name(note), DEFAULT_SHARE_NAME)

    def test_ignores_invisible_characters(self):
        self.assertEqual(default_share_name("<div>\u200b</div>"), DEFAULT_SHARE_NAME)
        self.assertEqual(default_share_name("\ufeff"), DEFAULT_SHARE_NAME)
        self.assertEqual(default_share_name("<div>\u200b</div><div>Real title</div>"), "Real title")

    def test_decodes_entities(self):
        self.assertEqual(default_share_name("<div>R&amp;D &lt;picks&gt;</div>"), "R&D <picks>")

    def test_truncates_long_lines_with_an_ellipsis(self):
        name = default_share_name("<div>" + ("x" * 200) + "</div>")
        self.assertEqual(len(name), DEFAULT_NAME_MAX_CHARS)
        self.assertTrue(name.endswith("…"))
