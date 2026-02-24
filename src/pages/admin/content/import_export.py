"""
JSON import/export utilities for Page and HomePage models.

Exports page content (html, css, grapesjs_json, dynamic_config, SEO fields)
to a portable JSON format.

Imported pages always arrive as draft.
"""

import logging
from datetime import UTC, datetime

from django.core.cache import cache
from django.db import transaction

from ...models import HomePage, Page

logger = logging.getLogger(__name__)

EXPORT_VERSION = "2.0"


# ========================
# Serialization
# ========================


def serialize_page(page):
    """Serialize a Page to an export dict."""
    return {
        "export_version": EXPORT_VERSION,
        "export_type": "page",
        "exported_at": datetime.now(UTC).isoformat(),
        "page": {
            "title": page.title,
            "slug": page.slug,
            "template_name": page.template_name,
            "html": page.html,
            "css": page.css,
            "grapesjs_json": page.grapesjs_json,
            "dynamic_config": page.dynamic_config,
            "meta_title": page.meta_title,
            "meta_description": page.meta_description,
            "meta_keywords": page.meta_keywords,
            "og_image": page.og_image or "",
            "canonical_url": page.canonical_url or "",
            "meta_robots": page.meta_robots,
            "google_site_verification": page.google_site_verification,
            "google_structured_data": page.google_structured_data,
        },
    }


def serialize_homepage(homepage):
    """Serialize a HomePage to an export dict."""
    return {
        "export_version": EXPORT_VERSION,
        "export_type": "homepage",
        "exported_at": datetime.now(UTC).isoformat(),
        "homepage": {
            "name": homepage.name,
            "html": homepage.html,
            "css": homepage.css,
            "grapesjs_json": homepage.grapesjs_json,
            "dynamic_config": homepage.dynamic_config,
        },
    }


# ========================
# Deserialization
# ========================


@transaction.atomic
def deserialize_page(data, user=None):
    """
    Import a Page from an export dict.

    - If a page with matching slug exists, update it.
    - Otherwise create a new page.
    - Imported pages always get status='draft'.

    Returns (page, warnings) where warnings is a list of strings.
    """
    warnings = []
    page_data = data.get("page", {})
    slug = page_data.get("slug", "")

    if not slug:
        raise ValueError("Import data missing required 'slug' field.")

    page = Page.objects.filter(slug=slug).first()
    if page:
        # Update existing page fields
        page.title = page_data.get("title", page.title)
        page.template_name = page_data.get("template_name", "")
        page.html = page_data.get("html", "")
        page.css = page_data.get("css", "")
        page.grapesjs_json = page_data.get("grapesjs_json", {})
        page.dynamic_config = page_data.get("dynamic_config", {})
        page.meta_title = page_data.get("meta_title", "")
        page.meta_description = page_data.get("meta_description", "")
        page.meta_keywords = page_data.get("meta_keywords", "")
        page.og_image = page_data.get("og_image", "") or None
        page.canonical_url = page_data.get("canonical_url", "") or None
        page.meta_robots = page_data.get("meta_robots", "")
        page.google_site_verification = page_data.get("google_site_verification", "")
        page.google_structured_data = page_data.get("google_structured_data")
        page.status = "draft"
        if user:
            page.updated_by = user
        page.save()
        warnings.append(f"Updated existing page '{slug}' (reset to draft).")
    else:
        # Create new page
        page = Page(
            title=page_data.get("title", slug),
            slug=slug,
            template_name=page_data.get("template_name", ""),
            html=page_data.get("html", ""),
            css=page_data.get("css", ""),
            grapesjs_json=page_data.get("grapesjs_json", {}),
            dynamic_config=page_data.get("dynamic_config", {}),
            meta_title=page_data.get("meta_title", ""),
            meta_description=page_data.get("meta_description", ""),
            meta_keywords=page_data.get("meta_keywords", ""),
            og_image=page_data.get("og_image", "") or None,
            canonical_url=page_data.get("canonical_url", "") or None,
            meta_robots=page_data.get("meta_robots", ""),
            google_site_verification=page_data.get("google_site_verification", ""),
            google_structured_data=page_data.get("google_structured_data"),
            status="draft",
        )
        if user:
            page.created_by = user
            page.updated_by = user
        page.save()

    # Invalidate page cache
    from ...models.pages.content.page import PAGE_CACHE_KEY_PREFIX

    cache.delete(f"{PAGE_CACHE_KEY_PREFIX}.slug.{page.slug}")
    cache.delete(f"{PAGE_CACHE_KEY_PREFIX}.list")

    return page, warnings


@transaction.atomic
def deserialize_homepage(data, user=None):
    """
    Import a HomePage from an export dict.

    - If a homepage with matching name exists, update it.
    - Otherwise create a new homepage.
    - Imported homepages always get status='draft', is_active=False.

    Returns (homepage, warnings) where warnings is a list of strings.
    """
    warnings = []
    hp_data = data.get("homepage", {})
    name = hp_data.get("name", "")

    if not name:
        raise ValueError("Import data missing required 'name' field.")

    homepage = HomePage.objects.filter(name=name).first()
    if homepage:
        homepage.html = hp_data.get("html", "")
        homepage.css = hp_data.get("css", "")
        homepage.grapesjs_json = hp_data.get("grapesjs_json", {})
        homepage.dynamic_config = hp_data.get("dynamic_config", {})
        homepage.status = "draft"
        homepage.is_active = False
        homepage.save()
        warnings.append(f"Updated existing homepage '{name}' (reset to draft, deactivated).")
    else:
        homepage = HomePage(
            name=name,
            html=hp_data.get("html", ""),
            css=hp_data.get("css", ""),
            grapesjs_json=hp_data.get("grapesjs_json", {}),
            dynamic_config=hp_data.get("dynamic_config", {}),
            status="draft",
            is_active=False,
        )
        homepage.save()

    # Invalidate homepage cache
    from ...models.pages.content.home_page import HOMEPAGE_CACHE_KEY

    cache.delete(HOMEPAGE_CACHE_KEY)

    return homepage, warnings
