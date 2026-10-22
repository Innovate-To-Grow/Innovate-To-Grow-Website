"""Which CSS classes does stored CMS content use, and what styles each one?

Admin-authored HTML (block ``body_html``, ``preamble_html``, ``footer_html``, ...; the
footer's ``contact_html`` and column HTML) can carry any class the sanitiser lets through,
and ``CMSPage.page_css_class`` adds classes to a page wrapper. None of that shows up when
scanning the React code, so this audit reads the stored content and reports, per class,
where it is used and what styles it:

* ``frontend_files``: frontend CSS in the entry bundle (loaded on every page) that defines it
  (see ``css_selectors`` for what "define" means);
* ``route_frontend_files``: frontend CSS that loads only once a lazily loaded route using it
  has been opened, so CMS content cannot rely on it;
* ``page_css``: routes whose own ``CMSPage.page_css`` defines it (it applies on that page only);
* ``scoped_in``: CSS that styles it only in context (inside another element, together with
  another class, in a nested rule);
* ``hook_in``: CSS that uses it as context for other elements (``.event-page`` in
  ``.event-page .x``), typical for page wrapper classes.

``defined`` is true only for a site-wide definition, which means an entry-bundle file.
A class that is neither defined nor a hook counts as having no site-wide definition.
Without the frontend sources (``scan_frontend=False``) no class reads as defined, so the
report then shows usage only.
"""

import re
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings

from apps.cms.models import CMSBlock, CMSPage, FooterContent

from .css_selectors import css_class_index
from .frontend_graph import entry_css_files, iter_css_files, read_text

HTML_KEY_SUFFIX = "_html"
# Browsers split a class attribute on ASCII whitespace only (a no-break space is part of a class).
_CLASS_SEPARATOR_RE = re.compile(r"[ \t\n\f\r]+")


def default_frontend_dir() -> Path:
    return Path(settings.BASE_DIR).parent / "pages" / "src"


def iter_html_fields(data):
    """Yield every string stored under a ``*_html`` key, however deeply nested."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(key, str) and key.endswith(HTML_KEY_SUFFIX) and isinstance(value, str):
                yield value
            else:
                yield from iter_html_fields(value)
    elif isinstance(data, list):
        for item in data:
            yield from iter_html_fields(item)


class _ClassCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.classes: set[str] = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "class" and value:
                self.classes.update(token for token in _CLASS_SEPARATOR_RE.split(value) if token)

    handle_startendtag = handle_starttag


def class_tokens_in_html(html) -> set[str]:
    collector = _ClassCollector()
    collector.feed(html or "")
    collector.close()
    return collector.classes


def _new_maps() -> dict:
    return {"defined": defaultdict(set), "scoped": defaultdict(set), "hook": defaultdict(set)}


def _index_into(maps: dict, css, label, *, defined_into=None) -> None:
    """Record ``label`` against every class ``css`` defines, scopes or uses as a hook."""
    index = css_class_index(css)
    for class_name in index.defined:
        (defined_into if defined_into is not None else maps["defined"])[class_name].add(label)
    for class_name in index.scoped:
        maps["scoped"][class_name].add(label)
    for class_name in index.context:
        maps["hook"][class_name].add(label)


def frontend_css_index(frontend_dir=None) -> dict:
    """Frontend CSS maps of class -> files: ``defined`` (entry bundle), ``route``, ``scoped``, ``hook``."""
    root = Path(frontend_dir or default_frontend_dir())
    maps = {**_new_maps(), "route": defaultdict(set), "graph": False}
    if not root.is_dir():
        return maps
    entry_files = entry_css_files(root)
    maps["graph"] = entry_files is not None
    for path in iter_css_files(root):
        relative = path.relative_to(root).as_posix()
        in_entry = entry_files is None or relative in entry_files
        _index_into(maps, read_text(path), relative, defined_into=None if in_entry else maps["route"])
    return maps


def page_css_index() -> dict:
    """Per-page CSS maps of class -> routes whose page_css defines, scopes or hooks on it."""
    maps = _new_maps()
    for page in CMSPage.objects.exclude(page_css="").only("route", "page_css"):
        _index_into(maps, page.page_css, page.route)
    return maps


def content_class_usage() -> dict[str, list[dict]]:
    """Class name -> one entry per block (any page status), page wrapper or active footer using it."""
    usage = defaultdict(list)
    for block in CMSBlock.objects.select_related("page").order_by("page__route", "sort_order"):
        classes = set().union(*(class_tokens_in_html(html) for html in iter_html_fields(block.data)))
        for class_name in classes:
            usage[class_name].append({"source": f"block:{block.block_type}", "where": block.page.route})
    for page in CMSPage.objects.exclude(page_css_class="").only("route", "page_css_class").order_by("route"):
        for class_name in set(page.page_css_class.split()):
            usage[class_name].append({"source": "page_css_class", "where": page.route})
    for footer in FooterContent.objects.filter(is_active=True).only("slug", "content").order_by("slug"):
        classes = set().union(*(class_tokens_in_html(html) for html in iter_html_fields(footer.content)))
        for class_name in classes:
            usage[class_name].append({"source": "footer", "where": f"footer:{footer.slug}"})
    return usage


def _labelled(maps_and_labels, class_name) -> list[str]:
    labels = []
    for maps, key, prefix in maps_and_labels:
        labels += [f"{prefix}{value}" for value in sorted(maps[key].get(class_name, ()))]
    return labels


def _row(class_name, uses, frontend, pages) -> dict:
    entry_files = sorted(frontend["defined"].get(class_name, ()))
    scoped_in = _labelled([(frontend, "scoped", ""), (pages, "scoped", "page_css:")], class_name)
    hook_in = _labelled([(frontend, "hook", ""), (pages, "hook", "page_css:")], class_name)
    wheres = {use["where"] for use in uses}
    return {
        "class_name": class_name,
        "usage_count": len(uses),
        "pages": sorted(where for where in wheres if not where.startswith("footer:")),
        "footers": sorted(where for where in wheres if where.startswith("footer:")),
        "sources": sorted({use["source"] for use in uses}),
        "block_types": sorted({use["source"][6:] for use in uses if use["source"].startswith("block:")}),
        "frontend_files": entry_files,
        "route_frontend_files": sorted(frontend["route"].get(class_name, ())),
        "page_css": sorted(pages["defined"].get(class_name, ())),
        "scoped_in": scoped_in,
        "hook_in": hook_in,
        "defined": bool(entry_files),
    }


def is_undefined(row: dict) -> bool:
    """No site-wide definition, and not a hook that other rules rely on."""
    return not row["defined"] and not row["hook_in"]


def audit_css_classes(frontend_dir=None, *, scan_frontend=True) -> dict:
    """The audit report: what was scanned, and one row per class used in stored CMS content.

    With ``scan_frontend=False`` (a server without the frontend sources) no frontend file
    is read, so no class reads as defined (``page_css`` is still read, but applies to one
    page only): the report then shows usage only.
    """
    root = Path(frontend_dir or default_frontend_dir())
    frontend = frontend_css_index(root) if scan_frontend else {**_new_maps(), "route": {}, "graph": False}
    usage = content_class_usage()
    pages = page_css_index()
    rows = [_row(class_name, usage[class_name], frontend, pages) for class_name in sorted(usage)]
    return {
        "frontend_scanned": scan_frontend,
        "frontend_dir": str(root) if scan_frontend else None,
        "frontend_import_graph": frontend["graph"],
        "total_classes": len(rows),
        "undefined_classes": sum(1 for row in rows if is_undefined(row)),
        "classes": rows,
    }
