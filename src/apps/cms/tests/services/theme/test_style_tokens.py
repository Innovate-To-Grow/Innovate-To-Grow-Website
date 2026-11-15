"""Tests for ``apps.cms.services.styles.tokens`` (design tokens rendered as ``--itg-*`` properties)."""

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.cms.services.styles.tokens import (
    MAX_TOKEN_VALUE_LENGTH,
    TOKEN_GROUP_PREFIX,
    token_variable_name,
)

LOGGER = "apps.cms.services.styles.tokens"


def _declarations(css):
    """The ``--itg-*`` declaration lines of a rendered ``:root`` block."""
    return [line.strip() for line in css.splitlines() if line.strip().startswith("--itg-")]


class TokenVariableNameTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_colors_group_gets_color_prefix(self):
        self.assertEqual(token_variable_name("colors", "primary_hover"), "--itg-color-primary-hover")

    def test_other_known_groups_get_no_prefix(self):
        for group in TOKEN_GROUP_PREFIX:
            if group == "colors":
                continue
            with self.subTest(group=group):
                self.assertEqual(token_variable_name(group, "font_size_h1"), "--itg-font-size-h1")

    def test_unknown_group_gets_no_prefix(self):
        self.assertEqual(token_variable_name("spacing", "gap_lg"), "--itg-gap-lg")


# Values refused by ``is_safe_token_value``, grouped by the rule that refuses them.
REFUSED_TOKEN_VALUES = {
    "backslash (CSS escape)": (
        "\\75 rl(https://example.com/x.png)",
        "\\72 ed",
        "re\\d",
        "red\\",
        "'Open Sans\\'",
    ),
    "line break or form feed": ("red\nblue", "red\rblue", "red\r\nblue", "red\fblue"),
    "other control character": (
        "red\tblue",
        "1px\t2px",
        "re\x00d",
        "red\x00",
        "\x00",
        "red\x01blue",
        "red\x0bblue",
        "red\x1bblue",
        "red\x7fblue",
        "red\x85blue",
        "red\x9fblue",
    ),
    # A lone surrogate cannot be encoded as UTF-8, so serving it would fail the whole stylesheet.
    "lone surrogate": ("red\ud800", "\udfff", "re\udc00d", "'Open Sans\ud83d'"),
    "rule or tag delimiter": ("red; color: blue", "red {", "red }", "a<b", "a>b"),
    "semicolon inside quotes": ("'a;b'", '"Open Sans;", serif'),
    "comment": ("1px /* c */", "/*", "'/*'"),
    "unbalanced bracket": (
        "rgba(0, 0, 0",
        "calc((1px + 2px)",
        "[x",
        "0 2px)",
        "x]",
        "([)]",
        "(]",
        ")(",
        "1px) rgba(0, 0, 0, 1) (",
        "]x[",
    ),
    "unclosed quote": ("'Open Sans", '"Open Sans', "'Open Sans', \"Arial", "it's"),
    "function that loads or reads something": (
        "url(https://example.com/x.png)",
        "URL(https://example.com/x.png)",
        "Url(x)",
        "url (x)",
        "image-set('a.png' 1x)",
        "IMAGE-SET('a.png' 1x)",
        "-webkit-image-set('a.png' 1x)",
        "src(x)",
        "image(x)",
        "cross-fade(a, b)",
        "element(#x)",
        "attr(data-x)",
        "env(safe-area-inset-top)",
        "expression(alert(1))",
        "url (x)",
        "1url(x)",
    ),
    "unknown function": (
        "foo()",
        "foo(1)",
        "-webkit-linear-gradient(red, blue)",
        "scaleX(2)",
        "--x(1)",
        "red (1)",
        "a-url(x)",
    ),
    "forbidden function nested in an allowed one": (
        "var(--x, url(a.png))",
        "calc(1px + attr(x))",
        "linear-gradient(red, blue), url(a.png)",
    ),
    "too long": ("a" * (MAX_TOKEN_VALUE_LENGTH + 1), "rgba(0, 0, 0, 0.5) " * 11),
}

ACCEPTED_TOKEN_VALUES = {
    "font stack": (
        "'Open Sans', Arial, sans-serif",
        '"Helvetica Neue", Helvetica, Arial, sans-serif',
        '"Kid\'s Font", \'Say "hi"\', serif',
        "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    ),
    "shadow": (
        "0 2px 8px rgba(15, 45, 82, 0.12)",
        "0 1px 2px rgba(0, 0, 0, 0.1), 0 4px 8px hsla(0, 0%, 0%, 0.2)",
        "inset 0 0 0 1px hsl(210 50% 40% / 0.2)",
    ),
    "maths and references": (
        "calc(100% - 2rem)",
        "calc(var(--itg-gap) * 2)",
        "var(--itg-color-primary)",
        "var(--itg-gap, 1rem)",
        "clamp(1rem, 2vw + 0.5rem, 3rem)",
        "min(100%, 1170px)",
        "max(50vh, calc((100% - 2rem) / 3))",
        "calc(100% - (2rem + 2px))",
    ),
    # Only a name followed by "(" is a call; a bare word is not checked against the function list.
    "names that are not called": ("url", "attr", "expression env", "var(--url)"),
    "colour": (
        "#0f2d52",
        "transparent",
        "rgb(0 0 0 / 50%)",
        "RGBA(0, 0, 0, 0.5)",
        "color-mix(in srgb, #0f2d52 80%, white)",
        "oklch(70% 0.1 250)",
    ),
    "gradient": (
        "linear-gradient(90deg, #fff 0%, rgb(0 0 0 / 50%) 100%)",
        "radial-gradient(circle at top, #fff, transparent)",
        "repeating-linear-gradient(45deg, #000 0 10px, #fff 10px 20px)",
    ),
    "timing, transform and grid": (
        "cubic-bezier(0.4, 0, 0.2, 1)",
        "steps(4, end)",
        "translateY(-2px)",
        "translateX(2px) rotate(45deg) scale(1.05)",
        "repeat(auto-fit, minmax(240px, 1fr))",
        "fit-content(20rem)",
    ),
    "brackets and function names inside quotes": (
        "'Open Sans (Bold)', serif",
        "'['",
        '")"',
        # A quoted "url(" is a string, not a call, so nothing is loaded.
        "'url(x)'",
    ),
    "length limit": ("a" * MAX_TOKEN_VALUE_LENGTH,),
    "non-ASCII text": (
        "'Noto Sans JP', '\u30d2\u30e9\u30ae\u30ce\u89d2\u30b4 ProN', sans-serif",
        "'\u00dcn\u00efc\u00f6d\u00e9 Sans'",
        # An astral character is one code point in Python, not a surrogate pair.
        "'Fira Sans \U0001f600'",
    ),
}
