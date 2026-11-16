"""The archive seed of ``resetdb``: CMS pages, menus and the footer from the exported JSON files in
``archive/data/`` (``python manage.py resetdb`` runs ``seed_archive_data`` after the reset)."""

import glob
import json
import os

from django.conf import settings

ARCHIVE_DATA_DIR = os.path.join(settings.BASE_DIR.parent, "archive", "data")


def seed_archive_data(command):
    """Seed CMS pages, menus, and footer from archive/data/."""
    if not os.path.isdir(ARCHIVE_DATA_DIR):
        command.stdout.write(command.style.WARNING(f"  Archive data directory not found: {ARCHIVE_DATA_DIR}"))
        return

    _seed_cms_pages(command)
    _seed_menus(command)
    _seed_footer(command)


def _seed_cms_pages(command):
    """Import CMS pages from the latest cms_export_*.json file."""
    matches = sorted(glob.glob(os.path.join(ARCHIVE_DATA_DIR, "cms_export_*.json")))
    if not matches:
        command.stdout.write("  No cms_export_*.json found, skipping CMS pages.")
        return

    filepath = matches[-1]  # latest by filename sort
    command.stdout.write(f"  Loading CMS pages from {os.path.basename(filepath)}...")
    with open(filepath) as f:
        bundle = json.load(f)

    pages_data = bundle.get("pages", [])
    if not pages_data:
        command.stdout.write("  No pages found in export file.")
        return

    from apps.cms.admin.cms.page_admin.import_export import process_page_data

    results = process_page_data(pages_data, action="execute", default_status="published", validate_required=False)
    created = sum(1 for r in results if r.get("success") and r.get("action") == "create")
    updated = sum(1 for r in results if r.get("success") and r.get("action") == "update")
    errors = sum(1 for r in results if r.get("errors"))
    command.stdout.write(command.style.SUCCESS(f"  CMS pages: {created} created, {updated} updated, {errors} errors."))


def _seed_menus(command):
    """Import menus from menus.json."""
    filepath = os.path.join(ARCHIVE_DATA_DIR, "menus.json")
    if not os.path.exists(filepath):
        command.stdout.write("  No menus.json found, skipping menus.")
        return

    command.stdout.write("  Loading menus...")
    with open(filepath) as f:
        items = json.load(f)

    from apps.cms.models import Menu

    menu, created = Menu.objects.update_or_create(
        name="main_nav",
        defaults={"display_name": "Main Navigation", "items": items, "is_active": True},
    )
    action = "Created" if created else "Updated"
    command.stdout.write(command.style.SUCCESS(f"  {action} menu 'main_nav' with {len(items)} top-level items."))


def _seed_footer(command):
    """Import footer content from footer.json."""
    filepath = os.path.join(ARCHIVE_DATA_DIR, "footer.json")
    if not os.path.exists(filepath):
        command.stdout.write("  No footer.json found, skipping footer.")
        return

    command.stdout.write("  Loading footer...")
    with open(filepath) as f:
        content = json.load(f)

    from apps.cms.models import FooterContent

    footer, created = FooterContent.objects.update_or_create(
        slug="default",
        defaults={"name": "Default Footer", "content": content, "is_active": True},
    )
    action = "Created" if created else "Updated"
    command.stdout.write(command.style.SUCCESS(f"  {action} footer 'default'."))
