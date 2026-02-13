"""
JSON import/export utilities for Page and HomePage models.

Exports page content (text fields, config, ordering, FK references by name/slug)
to a portable JSON format. Does NOT export PKs, user FKs, timestamps, file uploads,
view_count, or status — imported pages always arrive as draft.
"""

import logging
from datetime import datetime, timezone

from django.core.cache import cache
from django.db import transaction

from ..models import (
    ComponentDataSource,
    HomePage,
    Page,
    PageComponent,
    PageComponentImage,
    UniformForm,
)

logger = logging.getLogger(__name__)

EXPORT_VERSION = "1.0"


# ========================
# Serialization
# ========================


def _serialize_component(component):
    """Serialize a single PageComponent to a dict."""
    images = []
    for img in component.images.order_by("order", "id"):
        images.append(
            {
                "order": img.order,
                "alt": img.alt,
                "caption": img.caption,
                "link": img.link,
            }
        )

    return {
        "name": component.name,
        "component_type": component.component_type,
        "order": component.order,
        "is_enabled": component.is_enabled,
        "html_content": component.html_content,
        "css_code": component.css_code,
        "js_code": component.js_code,
        "config": component.config,
        "image_alt": component.image_alt,
        "image_caption": component.image_caption,
        "image_link": component.image_link,
        "background_image_alt": component.background_image_alt,
        "data_source_name": (
            component.data_source.source_name if component.data_source_id else None
        ),
        "form_slug": component.form.slug if component.form_id else None,
        "data_params": component.data_params,
        "refresh_interval_seconds": component.refresh_interval_seconds,
        "hydrate_on_client": component.hydrate_on_client,
        "images": images,
    }


def serialize_page(page):
    """Serialize a Page + its components + images to an export dict."""
    components = page.components.order_by("order", "id").prefetch_related("images")
    return {
        "export_version": EXPORT_VERSION,
        "export_type": "page",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "page": {
            "title": page.title,
            "slug": page.slug,
            "template_name": page.template_name,
            "meta_title": page.meta_title,
            "meta_description": page.meta_description,
            "meta_keywords": page.meta_keywords,
            "og_image": page.og_image or "",
            "canonical_url": page.canonical_url or "",
            "meta_robots": page.meta_robots,
            "google_site_verification": page.google_site_verification,
            "google_structured_data": page.google_structured_data,
        },
        "components": [_serialize_component(c) for c in components],
    }


def serialize_homepage(homepage):
    """Serialize a HomePage + its components + images to an export dict."""
    components = homepage.components.order_by("order", "id").prefetch_related("images")
    return {
        "export_version": EXPORT_VERSION,
        "export_type": "homepage",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "homepage": {
            "name": homepage.name,
        },
        "components": [_serialize_component(c) for c in components],
    }


# ========================
# Deserialization
# ========================


def _resolve_fk_refs(comp_data, warnings):
    """Resolve data_source and form FK references by name/slug."""
    data_source = None
    form = None

    ds_name = comp_data.get("data_source_name")
    if ds_name:
        data_source = ComponentDataSource.objects.filter(source_name=ds_name).first()
        if not data_source:
            warnings.append(f"Data source '{ds_name}' not found; skipped for component '{comp_data.get('name')}'.")

    form_slug = comp_data.get("form_slug")
    if form_slug:
        form = UniformForm.objects.filter(slug=form_slug).first()
        if not form:
            warnings.append(f"Form '{form_slug}' not found; skipped for component '{comp_data.get('name')}'.")

    return data_source, form


def _create_components(parent_field, parent, components_data, warnings):
    """Create PageComponent + PageComponentImage rows for a parent page/homepage."""
    for comp_data in components_data:
        data_source, form = _resolve_fk_refs(comp_data, warnings)

        component = PageComponent.objects.bulk_create(
            [
                PageComponent(
                    **{parent_field: parent},
                    name=comp_data.get("name", ""),
                    component_type=comp_data.get("component_type", "html"),
                    order=comp_data.get("order", 0),
                    is_enabled=comp_data.get("is_enabled", True),
                    html_content=comp_data.get("html_content", ""),
                    css_code=comp_data.get("css_code", ""),
                    js_code=comp_data.get("js_code", ""),
                    config=comp_data.get("config") or {},
                    image_alt=comp_data.get("image_alt", ""),
                    image_caption=comp_data.get("image_caption", ""),
                    image_link=comp_data.get("image_link", ""),
                    background_image_alt=comp_data.get("background_image_alt", ""),
                    data_source=data_source,
                    form=form,
                    data_params=comp_data.get("data_params") or {},
                    refresh_interval_seconds=comp_data.get("refresh_interval_seconds", 0),
                    hydrate_on_client=comp_data.get("hydrate_on_client", True),
                )
            ]
        )[0]

        # Create gallery images (skip file-based image field)
        images_data = comp_data.get("images", [])
        if images_data:
            PageComponentImage.objects.bulk_create(
                [
                    PageComponentImage(
                        component=component,
                        order=img.get("order", idx),
                        alt=img.get("alt", ""),
                        caption=img.get("caption", ""),
                        link=img.get("link", ""),
                    )
                    for idx, img in enumerate(images_data)
                ]
            )


@transaction.atomic
def deserialize_page(data, user=None):
    """
    Import a Page from an export dict.

    - If a page with matching slug exists, update it (replace all components).
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

    # Replace all components: hard_delete to avoid unique constraint violations
    PageComponent.objects.filter(page=page).hard_delete()

    # Create new components from import data
    _create_components("page", page, data.get("components", []), warnings)

    # Invalidate page cache after component replacement
    from ..models.pages.page import PAGE_CACHE_KEY_PREFIX

    cache.delete(f"{PAGE_CACHE_KEY_PREFIX}.slug.{page.slug}")
    cache.delete(f"{PAGE_CACHE_KEY_PREFIX}.list")

    return page, warnings


@transaction.atomic
def deserialize_homepage(data, user=None):
    """
    Import a HomePage from an export dict.

    - If a homepage with matching name exists, update it (replace all components).
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
        homepage.status = "draft"
        homepage.is_active = False
        homepage.save()
        warnings.append(f"Updated existing homepage '{name}' (reset to draft, deactivated).")
    else:
        homepage = HomePage(name=name, status="draft", is_active=False)
        homepage.save()

    # Replace all components
    PageComponent.objects.filter(home_page=homepage).hard_delete()

    _create_components("home_page", homepage, data.get("components", []), warnings)

    # Invalidate homepage cache after component replacement
    from ..models.pages.home_page import HOMEPAGE_CACHE_KEY

    cache.delete(HOMEPAGE_CACHE_KEY)

    return homepage, warnings
