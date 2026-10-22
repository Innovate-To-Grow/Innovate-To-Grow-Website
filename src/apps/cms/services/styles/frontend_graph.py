"""Which frontend CSS files load on every page of the SPA?

Vite puts CSS reached through *static* imports from ``src/main.tsx`` into the entry
bundle, which every page (CMS pages and embeds included) loads. CSS reached only through
``React.lazy(() => import(...))`` lands in a route chunk and loads only once a route that
uses it has been opened, so CMS content cannot rely on it. This module walks the static
import graph (``import`` / ``export ... from`` statements and CSS ``@import``) from the
entry module. Comments, regex literals and template literals are blanked first, type-only imports are
skipped, and bare package imports are not followed (except CSS ``@import "x.css"``,
which Vite resolves relative to the importing file first).
"""

import re
from pathlib import Path

ENTRY_MODULE = "main.tsx"
SKIPPED_DIRS = frozenset({"node_modules", "dist", "__tests__"})
_MODULE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs")
_TS_FOR_JS = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",)}
_STATIC_IMPORT_RE = re.compile(
    r"""(?:^|[;\n}])\s*(?:import|export)\s+(?:(type\s+(?!from\b))?[\w$*{},\s]*?\bfrom\s*)?['"]([^'"\n]+)['"]""",
)
_CSS_IMPORT_RE = re.compile(r"""@import\s+(?:url\(\s*['"]?([^'")\s]+)['"]?\s*\)|['"]([^'"]+)['"])""")
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def iter_css_files(root: Path):
    """Every readable ``*.css`` file under ``root``, skipping dependency, build and test dirs."""
    for path in sorted(root.rglob("*.css")):
        relative = path.relative_to(root)
        if SKIPPED_DIRS.intersection(relative.parts[:-1]) or not path.is_file():
            continue
        yield path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


_REGEX_PRECEDING_CHARS = frozenset("(,=:[!&|?{};+-*%>~^")
_REGEX_PRECEDING_WORDS = frozenset(
    {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "yield"}
)


def _regex_can_start(out: list[str]) -> bool:
    """Is a ``/`` here the start of a regex literal (rather than a division)?"""
    text = "".join(out[-40:]).rstrip()
    if not text:
        return True
    if text[-1] in _REGEX_PRECEDING_CHARS:
        return True
    word = text.split()[-1] if text.split() else ""
    return word in _REGEX_PRECEDING_WORDS


def _skip_regex(text: str, start: int) -> int:
    """Index just past the regex literal starting at ``start`` (flags included)."""
    i, in_class, length = start + 1, False, len(text)
    while i < length and text[i] != "\n":
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            i += 1
            while i < length and (text[i].isalnum() or text[i] == "_"):
                i += 1
            return i
        i += 1
    return i


def _skip_string(text: str, start: int) -> int:
    """Index of the closing quote of the string or template literal starting at ``start``."""
    quote, end, length = text[start], start + 1, len(text)
    while end < length and text[end] != quote and not (quote != "`" and text[end] == "\n"):
        end += 2 if text[end] == "\\" else 1
    return end


def strip_script_noise(text: str) -> str:
    """``text`` with comments, regex literals and template-literal contents blanked; '...'/"..." kept."""
    out, i, length = [], 0, len(text)
    while i < length:
        char, pair = text[i], text[i : i + 2]
        if pair == "//":
            end = text.find("\n", i)
            i = length if end == -1 else end
        elif pair == "/*":
            end = text.find("*/", i + 2)
            i = length if end == -1 else end + 2
            out.append(" ")
        elif char == "/" and _regex_can_start(out):
            i = _skip_regex(text, i)
            out.append("0")
        elif char in "'\"`":
            end = _skip_string(text, i)
            out.append("``" if char == "`" else text[i : end + 1])
            i = end + 1
        else:
            out.append(char)
            i += 1
    return "".join(out)


def _first_file(candidates) -> Path | None:
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _module_candidates(base: Path) -> list[Path]:
    if base.suffix == ".css":
        return [base]
    candidates = [base]
    if base.suffix in _TS_FOR_JS:
        candidates += [base.with_suffix(suffix) for suffix in _TS_FOR_JS[base.suffix]]
    if base.suffix not in _MODULE_SUFFIXES:
        candidates += [base.with_name(base.name + suffix) for suffix in _MODULE_SUFFIXES]
        candidates += [base / f"index{suffix}" for suffix in _MODULE_SUFFIXES]
    return candidates


def _resolve(specifier: str, importer: Path, root: Path) -> Path | None:
    if specifier.startswith("@/"):
        return _first_file(_module_candidates(root / specifier[2:]))
    if specifier.startswith(("./", "../")):
        return _first_file(_module_candidates(importer.parent / specifier))
    if importer.suffix == ".css" and ":" not in specifier:
        return _first_file([importer.parent / specifier])  # Vite: relative first for CSS
    return None  # a package from node_modules


def _static_specifiers(path: Path) -> list[str]:
    text = read_text(path)
    if path.suffix == ".css":
        return [url or quoted for url, quoted in _CSS_IMPORT_RE.findall(_CSS_COMMENT_RE.sub("", text))]
    code = strip_script_noise(text)
    return [specifier for type_only, specifier in _STATIC_IMPORT_RE.findall(code) if not type_only]


def entry_css_files(frontend_dir) -> set[str] | None:
    """Relative paths of the CSS files in the entry bundle, or ``None`` without an entry module."""
    root = Path(frontend_dir).resolve()
    entry = root / ENTRY_MODULE
    if not entry.is_file():
        return None
    seen: set[Path] = set()
    pending = [entry]
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        for specifier in _static_specifiers(module):
            target = _resolve(specifier, module, root)
            if target is not None and target not in seen:
                pending.append(target)
    return {path.relative_to(root).as_posix() for path in seen if path.suffix == ".css" and path.is_relative_to(root)}
