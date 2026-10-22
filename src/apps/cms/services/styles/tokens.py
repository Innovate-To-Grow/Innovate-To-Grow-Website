"""Design tokens (``SiteSettings.design_tokens``) rendered as CSS custom properties.

The tokens are a JSON object of groups, ``{"colors": {"primary": "#0f2d52"}, ...}``.
Each ``group.key`` becomes ``--itg-<prefix>-<key>``: the ``colors`` group gets the
``color`` prefix, the other known groups none. The values are written verbatim into a
``:root`` block at the top of the server-served stylesheet, so a value is emitted only
when it cannot end that block early, swallow the next declaration or load anything:

* no ``;``, ``{``, ``}``, ``<``, ``>``, backslash (CSS escapes), comment, control
  character (line breaks, tabs, NUL) or lone surrogate (which cannot be encoded);
* brackets ``()`` / ``[]`` balanced and every quoted string closed;
* functions limited to colour, maths, gradient and timing ones (``rgba()``, ``calc()``,
  ``var()``, ...), so ``url()``, ``image-set()`` and the like are refused;
* at most ``MAX_TOKEN_VALUE_LENGTH`` characters.

A refused token is left out and logged as a warning; the other tokens still render.
"""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

TOKEN_GROUP_PREFIX = {
    "colors": "color",
    "typography": "",
    "typography_mobile": "",
    "layout": "",
    "borders": "",
    "effects": "",
}

MAX_TOKEN_VALUE_LENGTH = 200

ALLOWED_TOKEN_FUNCTIONS = frozenset(
    {
        # colours
        "rgb", "rgba", "hsl", "hsla", "hwb", "lab", "lch", "oklab", "oklch", "color", "color-mix", "light-dark",
        # maths and references
        "var", "calc", "min", "max", "clamp", "round", "mod", "rem", "abs", "sign",
        # gradients, easing, transforms and grid sizes
        "linear-gradient", "radial-gradient", "conic-gradient",
        "repeating-linear-gradient", "repeating-radial-gradient", "repeating-conic-gradient",
        "cubic-bezier", "steps", "translate", "translatex", "translatey", "scale", "rotate",
        "fit-content", "minmax", "repeat",
    }
)  # fmt: skip

_TOKEN_KEY_RE = re.compile(r"^[a-z0-9_]+$")
_FORBIDDEN_CHARS = frozenset(";{}<>\\\n\r\f")
_FUNCTION_RE = re.compile(r"(-?[A-Za-z_][\w-]*)\s*\(")
_CLOSERS = {")": "(", "]": "["}


def token_variable_name(group: str, key: str) -> str:
    """The ``--itg-*`` custom property name for ``group.key``."""
    prefix = TOKEN_GROUP_PREFIX.get(group, "")
    kebab = key.replace("_", "-")
    return f"--itg-{prefix}-{kebab}" if prefix else f"--itg-{kebab}"


def is_safe_token_key(key) -> bool:
    return isinstance(key, str) and bool(_TOKEN_KEY_RE.fullmatch(key))


def _unquoted_text(text: str) -> str | None:
    """``text`` with quoted strings blanked out, or ``None`` if a bracket or quote is unbalanced."""
    stack: list[str] = []
    quote = None
    kept = []
    for char in text:
        if quote:
            if char == quote:
                quote = None
            kept.append(" ")
            continue
        if char in "'\"":
            quote = char
            kept.append(" ")
            continue
        if char in "([":
            stack.append(char)
        elif char in _CLOSERS:
            if not stack or stack.pop() != _CLOSERS[char]:
                return None
        kept.append(char)
    if quote or stack:
        return None
    return "".join(kept)


def is_safe_token_value(text: str) -> bool:
    if not text or len(text) > MAX_TOKEN_VALUE_LENGTH:
        return False
    if "/*" in text or any(char in _FORBIDDEN_CHARS for char in text):
        return False
    if any(unicodedata.category(char) in ("Cc", "Cs") for char in text):
        return False
    unquoted = _unquoted_text(text)
    if unquoted is None:
        return False
    return all(name.lower() in ALLOWED_TOKEN_FUNCTIONS for name in _FUNCTION_RE.findall(unquoted))


def coerce_token_value(value) -> str | None:
    """Return the CSS text for a token value, or ``None`` when it must not be emitted."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        value = str(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if is_safe_token_value(text) else None


def _render_group(group: str, values: dict) -> list[str]:
    lines = []
    for key, value in values.items():
        if not is_safe_token_key(key):
            logger.warning("Design token %r.%r skipped: keys must match [a-z0-9_]+", group, key)
            continue
        text = coerce_token_value(value)
        if text is None:
            logger.warning("Design token %r.%r skipped: unsafe or non-text value %r", group, key, value)
            continue
        lines.append(f"  {token_variable_name(group, key)}: {text};")
    return lines


def render_tokens_css(tokens) -> str:
    """Render the design-token JSON as a ``:root`` block, or ``""`` when nothing is usable."""
    if not isinstance(tokens, dict):
        return ""
    lines = []
    for group, values in tokens.items():
        if not isinstance(values, dict):
            continue
        if group not in TOKEN_GROUP_PREFIX:
            logger.warning("Design token group %r is not a known group; its tokens get no prefix", group)
        lines.extend(_render_group(group, values))
    if not lines:
        return ""
    return ":root {\n" + "\n".join(lines) + "\n}\n"
