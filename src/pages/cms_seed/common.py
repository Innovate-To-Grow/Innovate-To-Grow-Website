"""Shared helpers for CMS seed commands."""

from django.core.management.base import BaseCommand

from pages.models import CMSBlock, CMSPage


def add_seed_arguments(command: BaseCommand, parser) -> None:
    parser.add_argument("--page", type=str, help="Seed a specific page by slug. Omit to seed all.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing pages.")


def handle_seed_pages(command: BaseCommand, pages_to_seed, *, target_slug: str | None, force: bool) -> None:
    selected_pages = list(pages_to_seed)
    if target_slug:
        selected_pages = [page for page in selected_pages if page["slug"] == target_slug]
        if not selected_pages:
            command.stderr.write(f"No seed data found for slug '{target_slug}'.")
            return

    for page_data in selected_pages:
        _seed_page(command, page_data, force=force)

    command.stdout.write(command.style.SUCCESS("Done."))


def _seed_page(command: BaseCommand, page_data, *, force: bool) -> None:
    slug = page_data["slug"]
    existing = CMSPage.objects.filter(slug=slug).first()

    if existing and not force:
        command.stdout.write(f"  Skipping '{slug}' - already exists. Use --force to overwrite.")
        return
    if existing and force:
        existing.hard_delete()
        command.stdout.write(f"  Deleted existing '{slug}'.")

    page = CMSPage.objects.create(
        slug=page_data["slug"],
        route=page_data["route"],
        title=page_data["title"],
        page_css_class=page_data.get("page_css_class", ""),
        status="published",
    )
    for block_data in page_data.get("blocks", []):
        CMSBlock.objects.create(
            page=page,
            block_type=block_data["block_type"],
            sort_order=block_data["sort_order"],
            admin_label=block_data.get("admin_label", ""),
            data=block_data["data"],
        )
    command.stdout.write(command.style.SUCCESS(f"  Created '{slug}' with {len(page_data['blocks'])} block(s)."))
