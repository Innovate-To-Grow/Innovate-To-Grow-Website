from django.test import SimpleTestCase

from apps.core.utils.text import collapse_whitespace, normalize_paragraphs


class CollapseWhitespaceTest(SimpleTestCase):
    def test_collapses_double_spaces_tabs_and_nbsp(self):
        self.assertEqual(collapse_whitespace("UC Merced Sustainability  Office"), "UC Merced Sustainability Office")
        self.assertEqual(collapse_whitespace("Ada Lovelace,\tBen Ng"), "Ada Lovelace, Ben Ng")

    def test_strips_and_joins_lines(self):
        self.assertEqual(collapse_whitespace("  Smart\nFarm  "), "Smart Farm")

    def test_empty_values(self):
        self.assertEqual(collapse_whitespace(""), "")
        self.assertEqual(collapse_whitespace(None), "")


class NormalizeParagraphsTest(SimpleTestCase):
    def test_collapses_spaces_inside_lines(self):
        self.assertEqual(normalize_paragraphs("Sentence one.   Sentence  two."), "Sentence one. Sentence two.")

    def test_keeps_paragraph_breaks(self):
        self.assertEqual(normalize_paragraphs("First.  \r\n\r\n\r\n  Second.\nThird."), "First.\n\nSecond.\nThird.")

    def test_strips_outer_whitespace(self):
        self.assertEqual(normalize_paragraphs("\n  Abstract text \n"), "Abstract text")
