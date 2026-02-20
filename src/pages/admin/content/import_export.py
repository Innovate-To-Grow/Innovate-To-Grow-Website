"""
JSON import/export utilities for Page and HomePage models.

Exports page content (text fields, config, ordering, FK references by name/slug)
to a portable JSON format. Optionally includes file field paths for ZIP-based
export/import with media files.

Imported pages always arrive as draft.
"""

import logging
import os
from datetime import UTC, datetime

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db import transaction

from ...models import (
    ComponentDataSource,
    GoogleSheet,
    HomePage,
    Page,
    PageComponent,
    PageComponentImage,
    PageComponentPlacement,
    UniformForm,
)

logger = logging.getLogger(__name__)

EXPORT_VERSION = "1.0"
ZIP_EXPORT_VERSION = "2.0"


# ========================
# Serialization
# ========================


def _serialize_component(component, order, include_files=False):
    """Serialize a single PageComponent to a dict.

    Args:
        order: The placement order for this component in its parent context.
        include_files: When True, include storage-relative paths for file fields
                       (css_file, image, background_image, gallery images).
    """
    images = []
    for img in component.images.order_by("order", "id"):
        img_data = {
            "order": img.order,
            "alt": img.alt,
            "caption": img.caption,
            "link": img.link,
        }
        if include_files:
            img_data["image"] = img.image.name if img.image else None
        images.append(img_data)

    data = {
        "name": component.name,
        "component_type": component.component_type,
        "order": order,
        "is_enabled": component.is_enabled,
        "html_content": component.html_content,
        "css_code": component.css_code,
        "js_code": component.js_code,
        "config": component.config,
        "image_alt": component.image_alt,
        "image_caption": component.image_caption,
        "image_link": component.image_link,
        "background_image_alt": component.background_image_alt,
        "data_source_name": (component.data_source.source_name if component.data_source_id else None),
        "form_slug": component.form.slug if component.form_id else None,
        "google_sheet_name": component.google_sheet.name if component.google_sheet_id else None,
        "google_sheet_style": component.google_sheet_style,
        "data_params": component.data_params,
        "refresh_interval_seconds": component.refresh_interval_seconds,
        "hydrate_on_client": component.hydrate_on_client,
        "images": images,
    }

    if include_files:
        data["css_file"] = component.css_file.name if component.css_file else None
        data["image"] = component.image.name if component.image else None
        data["background_image"] = component.background_image.name if component.background_image else None

    return data


def serialize_page(page, include_files=False):
    """Serialize a Page + its components + images to an export dict."""
    placements = page.component_placements.select_related(
        "component", "component__data_source", "component__form", "component__google_sheet"
    ).prefetch_related("component__images").order_by("order", "id")
    return {
        "export_version": EXPORT_VERSION,
        "export_type": "page",
        "exported_at": datetime.now(UTC).isoformat(),
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
        "components": [
            _serialize_component(p.component, order=p.order, include_files=include_files)
            for p in placements
        ],
    }


def serialize_homepage(homepage, include_files=False):
    """Serialize a HomePage + its components + images to an export dict."""
    placements = homepage.component_placements.select_related(
        "component", "component__data_source", "component__form", "component__google_sheet"
    ).prefetch_related("component__images").order_by("order", "id")
    return {
        "export_version": EXPORT_VERSION,
        "export_type": "homepage",
        "exported_at": datetime.now(UTC).isoformat(),
        "homepage": {
            "name": homepage.name,
        },
        "components": [
            _serialize_component(p.component, order=p.order, include_files=include_files)
            for p in placements
        ],
    }


# ========================
# Deserialization
# ========================


def _resolve_fk_refs(comp_data, warnings):
    """Resolve data_source, form, and google_sheet FK references by name/slug."""
    data_source = None
    form = None
    google_sheet = None

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

    google_sheet_name = comp_data.get("google_sheet_name")
    if google_sheet_name:
        google_sheet = GoogleSheet.objects.filter(name=google_sheet_name).first()
        if not google_sheet:
            warnings.append(
                f"Google Sheet '{google_sheet_name}' not found; skipped for component '{comp_data.get('name')}'."
            )

    return data_source, form, google_sheet


def _create_components(parent_field, parent, components_data, warnings, file_map=None):
    """Create PageComponent + PageComponentPlacement + PageComponentImage rows for a parent.

    Args:
        file_map: Optional dict mapping archive paths (``media/{storage_path}``)
                  to raw ``bytes``.  When provided, file fields are restored from
                  the archive data.
    """
    valid_types = {"html", "markdown", "form", "table", "google_sheet"}

    for comp_data in components_data:
        data_source, form, google_sheet = _resolve_fk_refs(comp_data, warnings)

        # Convert deprecated component types to html
        comp_type = comp_data.get("component_type", "html")
        if comp_type not in valid_types:
            warnings.append(
                f"Component '{comp_data.get('name')}' had unsupported type '{comp_type}', defaulted to 'html'."
            )
            comp_type = "html"

        if comp_type == "google_sheet" and not google_sheet:
            warnings.append(
                f"Component '{comp_data.get('name')}' had unresolved google_sheet_name and was defaulted to 'html'."
            )
            comp_type = "html"

        google_sheet_style = comp_data.get("google_sheet_style", PageComponent.GoogleSheetStyle.DEFAULT)
        style_values = {choice[0] for choice in PageComponent.GoogleSheetStyle.choices}
        if google_sheet_style not in style_values:
            warnings.append(
                f"Component '{comp_data.get('name')}' had unsupported google_sheet_style "
                f"'{google_sheet_style}', defaulted to '{PageComponent.GoogleSheetStyle.DEFAULT}'."
            )
            google_sheet_style = PageComponent.GoogleSheetStyle.DEFAULT

        component = PageComponent.objects.bulk_create(
            [
                PageComponent(
                    name=comp_data.get("name", ""),
                    component_type=comp_type,
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
                    google_sheet=google_sheet if comp_type == "google_sheet" else None,
                    google_sheet_style=google_sheet_style,
                    data_params=comp_data.get("data_params") or {},
                    refresh_interval_seconds=comp_data.get("refresh_interval_seconds", 0),
                    hydrate_on_client=comp_data.get("hydrate_on_client", True),
                )
            ]
        )[0]

        # Create the placement linking component to parent
        PageComponentPlacement.objects.bulk_create(
            [
                PageComponentPlacement(
                    component=component,
                    **{parent_field: parent},
                    order=comp_data.get("order", 0),
                )
            ]
        )

        # Restore file fields from archive
        if file_map is not None:
            _restore_component_files(component, comp_data, file_map, warnings)

        # Create gallery images
        images_data = comp_data.get("images", [])
        if images_data:
            img_objects = PageComponentImage.objects.bulk_create(
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
            # Restore gallery image files from archive
            if file_map is not None:
                for img_obj, img_data in zip(img_objects, images_data, strict=False):
                    _restore_image_file(img_obj, img_data, file_map, warnings)


@transaction.atomic
def deserialize_page(data, user=None, file_map=None):
    """
    Import a Page from an export dict.

    - If a page with matching slug exists, update it (replace all components).
    - Otherwise create a new page.
    - Imported pages always get status='draft'.

    Args:
        file_map: Optional dict mapping archive paths to raw bytes for file restoration.

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

    # Delete placements and orphaned components
    component_ids = list(
        PageComponentPlacement.objects.filter(page=page).values_list("component_id", flat=True)
    )
    PageComponentPlacement.objects.filter(page=page).hard_delete()
    PageComponent.objects.filter(
        id__in=component_ids,
        placements__isnull=True,
    ).hard_delete()

    # Create new components from import data
    _create_components("page", page, data.get("components", []), warnings, file_map=file_map)

    # Invalidate page cache after component replacement
    from ...models.pages.content.page import PAGE_CACHE_KEY_PREFIX

    cache.delete(f"{PAGE_CACHE_KEY_PREFIX}.slug.{page.slug}")
    cache.delete(f"{PAGE_CACHE_KEY_PREFIX}.list")

    return page, warnings


@transaction.atomic
def deserialize_homepage(data, user=None, file_map=None):
    """
    Import a HomePage from an export dict.

    - If a homepage with matching name exists, update it (replace all components).
    - Otherwise create a new homepage.
    - Imported homepages always get status='draft', is_active=False.

    Args:
        file_map: Optional dict mapping archive paths to raw bytes for file restoration.

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

    # Delete placements and orphaned components
    component_ids = list(
        PageComponentPlacement.objects.filter(home_page=homepage).values_list("component_id", flat=True)
    )
    PageComponentPlacement.objects.filter(home_page=homepage).hard_delete()
    PageComponent.objects.filter(
        id__in=component_ids,
        placements__isnull=True,
    ).hard_delete()

    _create_components("home_page", homepage, data.get("components", []), warnings, file_map=file_map)

    # Invalidate homepage cache after component replacement
    from ...models.pages.content.home_page import HOMEPAGE_CACHE_KEY

    cache.delete(HOMEPAGE_CACHE_KEY)

    return homepage, warnings


# ========================
# File helpers
# ========================


def collect_component_files(components_queryset):
    """Collect all storage-relative file paths referenced by a set of components.

    Returns a set of paths like ``page_components/images/hero.png``
    (the ``.name`` value from each FileField/ImageField).
    """
    file_paths = set()
    for component in components_queryset.prefetch_related("images"):
        if component.css_file:
            file_paths.add(component.css_file.name)
        if component.image:
            file_paths.add(component.image.name)
        if component.background_image:
            file_paths.add(component.background_image.name)
        for img in component.images.all():
            if img.image:
                file_paths.add(img.image.name)
    return file_paths


def _restore_component_files(component, comp_data, file_map, warnings):
    """Assign file fields on a PageComponent from archive *file_map*.

    Uses ``queryset.update()`` to persist path strings without triggering
    ``PageComponent.save()`` / ``full_clean()`` which may reject partial
    objects during import.
    """
    _COMPONENT_FILE_FIELDS = ("css_file", "image", "background_image")
    update_kwargs = {}

    for field_name in _COMPONENT_FILE_FIELDS:
        rel_path = comp_data.get(field_name)
        if not rel_path:
            continue
        archive_key = f"media/{rel_path}" if not rel_path.startswith("media/") else rel_path
        file_bytes = file_map.get(archive_key)
        if file_bytes is not None:
            field = getattr(component, field_name)
            field.save(os.path.basename(rel_path), ContentFile(file_bytes), save=False)
            update_kwargs[field_name] = field.name
        else:
            warnings.append(
                f"File '{rel_path}' for component '{comp_data.get('name')}' field '{field_name}' not found in archive."
            )

    if update_kwargs:
        PageComponent.objects.filter(pk=component.pk).update(**update_kwargs)


def _restore_image_file(img_obj, img_data, file_map, warnings):
    """Assign image file on a PageComponentImage from archive *file_map*."""
    rel_path = img_data.get("image")
    if not rel_path:
        return
    archive_key = f"media/{rel_path}" if not rel_path.startswith("media/") else rel_path
    file_bytes = file_map.get(archive_key)
    if file_bytes is not None:
        img_obj.image.save(os.path.basename(rel_path), ContentFile(file_bytes), save=False)
        PageComponentImage.objects.filter(pk=img_obj.pk).update(image=img_obj.image.name)
    else:
        warnings.append(
            f"Image file '{rel_path}' for gallery image (order {img_data.get('order')}) not found in archive."
        )
