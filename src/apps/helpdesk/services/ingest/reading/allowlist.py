"""What sanitizing keeps of inbound HTML (``sanitize``): the allow-listed tags, attributes, link schemes and CSS
properties, and the elements it removes together with everything inside them."""

ALLOWED_TAGS = frozenset(
    {
        "a", "abbr", "b", "blockquote", "br", "caption", "center", "cite", "code", "col", "colgroup", "dd", "del",
        "div", "dl", "dt", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "ins", "kbd", "li", "ol",
        "p", "pre", "q", "s", "small", "span", "strike", "strong", "sub", "sup", "table", "tbody", "td", "tfoot",
        "th", "thead", "tr", "tt", "u", "ul",
    }
)  # fmt: skip
# The phrasing elements among them: formatting a mail program may put inside a link's text.
INLINE_TAGS = (
    "a", "abbr", "b", "cite", "code", "del", "em", "font", "i", "ins", "kbd", "q", "s", "small", "span", "strike",
    "strong", "sub", "sup", "tt", "u",
)  # fmt: skip
_CELL = ["colspan", "rowspan", "width", "height", "bgcolor", "align", "valign", "nowrap"]
ALLOWED_ATTRIBUTES = {
    "*": ["style", "title", "dir", "lang", "align"],
    "a": ["href", "title"],
    "td": _CELL,
    "th": _CELL,
    "table": ["width", "border", "cellpadding", "cellspacing", "bgcolor", "align"],
    "col": ["span", "width"],
    "colgroup": ["span", "width"],
    "font": ["color", "face", "size"],
    "ol": ["start", "type"],
    "ul": ["type"],
}
ALLOWED_PROTOCOLS = frozenset({"http", "https", "mailto", "tel"})
ALLOWED_CSS_PROPERTIES = frozenset(
    {
        "color", "background-color", "font", "font-family", "font-size", "font-style", "font-weight",
        "font-variant", "text-align", "text-decoration", "text-indent", "text-transform", "line-height",
        "letter-spacing", "word-spacing", "white-space", "vertical-align", "margin", "margin-top", "margin-right",
        "margin-bottom", "margin-left", "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
        "border", "border-top", "border-right", "border-bottom", "border-left", "border-color", "border-style",
        "border-width", "border-collapse", "border-spacing", "border-radius", "width", "height", "max-width",
        "min-width", "list-style-type",
    }
)  # fmt: skip
# Removed together with everything inside them.
DROPPED_WITH_CONTENT = (
    "script", "style", "iframe", "frame", "frameset", "object", "embed", "applet", "form", "svg", "math", "base",
    "meta", "link", "head", "title", "noscript", "template", "audio", "video", "canvas", "button", "input", "select",
    "textarea", "picture", "source", "track", "map", "area",
)  # fmt: skip
