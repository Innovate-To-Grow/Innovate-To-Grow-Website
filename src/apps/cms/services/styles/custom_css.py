"""Checks for the Site Settings custom CSS, served in ``itg.overrides`` of /layout/theme.css.

tinycss2 reads the CSS the way a browser does, so these checks catch what would break the sheet
(unbalanced braces, rules the parser drops) and the constructs custom CSS must not use. They
cannot catch a misspelled property: the browser ignores that declaration and nothing else.
"""

import tinycss2

MAX_CUSTOM_CSS_BYTES = 64 * 1024
# At-rules that must open a stylesheet, so inside the itg.overrides block they would be dropped
# (and @import would load CSS from elsewhere).
FORBIDDEN_AT_RULES = frozenset({"import", "charset", "namespace"})
FORBIDDEN_PROPERTIES = frozenset({"behavior", "-moz-binding"})
FORBIDDEN_FUNCTIONS = frozenset({"expression"})
NESTED_AT_RULES = frozenset({"media", "supports", "layer", "container", "scope", "starting-style"})


def _where(node) -> str:
    return f"Line {node.source_line}, column {node.source_column}"


def _skipped_end(css: str, index: int) -> int | None:
    """Where the comment or string that starts at ``index`` ends; None for any other character."""
    if css.startswith("/*", index):
        end = css.find("*/", index + 2)
        return len(css) if end == -1 else end + 2
    quote = css[index]
    if quote not in "\"'":
        return None
    end = index + 1
    while end < len(css) and css[end] not in (quote, "\n"):
        end += 2 if css[end] == "\\" else 1
    return min(end + 1, len(css))


def _brace_errors(css: str) -> list[str]:
    """An unclosed ``{`` would swallow the rest of the sheet; a stray ``}`` would end the layer block."""
    errors, stack = [], []
    line, column, index = 1, 1, 0
    while index < len(css):
        end = _skipped_end(css, index)
        if end is None:
            if css[index] == "{":
                stack.append((line, column))
            elif css[index] == "}" and stack:
                stack.pop()
            elif css[index] == "}":
                errors.append(f"Line {line}, column {column}: this }} closes no block.")
            end = index + 1
        for skipped in css[index:end]:
            line, column = (line + 1, 1) if skipped == "\n" else (line, column + 1)
        index = end
    errors += [f"Line {at_line}, column {at_column}: this {{ is never closed." for at_line, at_column in stack]
    return errors


def _value_errors(tokens, where) -> list[str]:
    errors = []
    for token in tokens:
        if token.type == "error":
            errors.append(f"{where}: {token.message}.")
        elif token.type == "function" and token.lower_name in FORBIDDEN_FUNCTIONS:
            errors.append(f"{where}: {token.name}() is not allowed.")
        elif token.type == "url" and token.value.strip().lower().startswith("javascript:"):
            errors.append(f"{where}: javascript: URLs are not allowed.")
        if token.type == "function" and token.lower_name == "url":
            target = "".join(getattr(arg, "value", "") or "" for arg in token.arguments).strip().lower()
            if target.startswith("javascript:"):
                errors.append(f"{where}: javascript: URLs are not allowed.")
        if getattr(token, "content", None) is not None and token.type != "url":
            errors += _value_errors(token.content, where)
        if token.type == "function":
            errors += _value_errors(token.arguments, where)
    return errors


def _block_errors(nodes) -> list[str]:
    errors = []
    for node in nodes:
        if node.type == "error":
            errors.append(f"{_where(node)}: {node.message}.")
        elif node.type == "at-rule":
            if node.lower_at_keyword in FORBIDDEN_AT_RULES:
                errors.append(f"{_where(node)}: @{node.at_keyword} is not allowed in custom CSS.")
            elif node.content is not None:
                errors += _block_errors(tinycss2.parse_blocks_contents(node.content, True, True))
        elif node.type == "qualified-rule":
            errors += _value_errors(node.prelude, _where(node))
            errors += _block_errors(tinycss2.parse_blocks_contents(node.content, True, True))
        elif node.type == "declaration":
            if node.lower_name in FORBIDDEN_PROPERTIES:
                errors.append(f"{_where(node)}: the {node.name} property is not allowed.")
            errors += _value_errors(node.value, _where(node))
    return errors


def custom_css_errors(css: str) -> list[str]:
    """Problems that keep ``css`` out of the theme sheet; an empty list means it is fine."""
    size = len(css.encode("utf-8"))
    if size > MAX_CUSTOM_CSS_BYTES:
        return [f"Custom CSS is {size} bytes; the limit is {MAX_CUSTOM_CSS_BYTES}."]
    errors = _brace_errors(css)
    errors += _block_errors(tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True))
    return errors
