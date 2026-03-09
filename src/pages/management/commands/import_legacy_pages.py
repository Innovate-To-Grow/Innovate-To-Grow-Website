"""
Import static HTML pages from the legacy Flask site into the Page model.

Reads HTML templates from the old Flask site's templates/home/ directory and
creates (or updates) Page objects with status="published".

Slug mapping is derived from the original Flask route definitions in
project/views/home.py. Routes that used uppercase or underscores are
normalized to lowercase-with-hyphens to satisfy the slug validator.

Idempotent by default: existing pages are skipped unless --update is passed.
"""

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from pages.models import Page

# ---------------------------------------------------------------------------
# Route mapping  (template filename without .html  →  route path without /)
# Derived from project/views/home.py.  Routes are normalized so that:
#   - uppercase → lowercase
#   - underscores → hyphens
# ---------------------------------------------------------------------------

TEMPLATE_ROUTE_MAP: dict[str, str] = {
    # mainpage "/" also serves home-post-event; mapped via its explicit route
    "home-post-event": "home-post-event",
    "about": "about",
    "terms_and_conditions": "privacy",
    "engineering-capstone": "engineering-capstone",
    "about_EngSL": "about-engsl",
    "software-capstone": "software-capstone",
    "event": "event",
    "schedule": "schedule",
    "projects-teams": "projects-teams",
    "judges": "judges",
    "attendees": "attendees",
    "students": "students",
    "acknowledgement": "acknowledgement",
    "past-events": "past-events",
    "projects": "projects",
    "current-projects": "current-projects",
    "project-submission": "project-submission",
    "sample-proposals": "sample-proposals",
    "partnership": "partnership",
    "sponsorship": "sponsorship",
    "faq": "faqs",
    "I2G-student-agreement": "i2g-student-agreement",
    "ferpa": "ferpa",
    "i2g-students-preparation": "i2g-students-preparation",
    "video-preparation": "video-preparation",
    "capstone-purchasing-reimbursement": "capstone-purchasing-reimbursement",
    "contact-us": "contact-us",
    "judging": "judging",
    "template": "template",
    "template-email-team-students": "template-email-team-students",
    "I2G-project-sponsor-acknowledgement": "i2g-project-sponsor-acknowledgement",
    "home-during-event": "home-during-event",
    "2025-fall-event": "2025-fall-event",
    "2025-spring-event": "2025-spring-event",
    "2024-fall-event": "2024-fall-event",
    "2023-fall-event": "2023-fall-event",
    "2023-spring-event": "2023-spring-event",
    "2024-spring-event": "2024-spring-event",
    "2022-fall-event": "2022-fall-event",
    "2022-spring-event": "2022-spring-event",
    "2021-spring-event": "2021-spring-event",
    "2021-fall-event": "2021-fall-event",
    "2020-fall-post-event": "2020-fall-post-event",
    "2014-sponsors": "2014-sponsors",
    "2015-sponsors": "2015-sponsors",
    "past-projects": "past-projects",
    # No explicit route in home.py — use filename-derived slug
    "home-pre-event": "home-pre-event",
    "home-during-semester": "home-during-semester",
}

_SLUG_VALID_RE = re.compile(r"^[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:/[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)*$")


def _filename_to_title(stem: str) -> str:
    """Convert a filename stem like 'about_EngSL' to a readable title."""
    return stem.replace("-", " ").replace("_", " ").title()


def _normalize_slug_segment(segment: str) -> str:
    """Lowercase and replace underscores with hyphens in a single slug segment."""
    return segment.lower().replace("_", "-")


class Command(BaseCommand):
    help = "Import legacy Flask HTML templates as published Page objects."

    def add_arguments(self, parser):
        parser.add_argument(
            "--templates-dir",
            default=r"C:\_py\Innovate-To-Grow-Website-Old\project\templates\home",
            help="Path to the Flask templates/home directory (default: %(default)s).",
        )
        parser.add_argument(
            "--prefix",
            default="legacy",
            help="Slug prefix prepended to every page slug (default: %(default)s).",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            default=False,
            help="Overwrite html content of pages that already exist.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be created/updated without writing to the database.",
        )

    def handle(self, *args, **options):
        templates_dir = Path(options["templates_dir"])
        if not templates_dir.is_dir():
            raise CommandError(f"Templates directory not found: {templates_dir}")

        prefix = options["prefix"].strip("/")
        if not prefix:
            raise CommandError("--prefix cannot be empty.")

        do_update = options["update"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run mode — no database writes."))

        html_files = sorted(templates_dir.glob("*.html"))
        if not html_files:
            raise CommandError(f"No .html files found in {templates_dir}")

        created = updated = skipped = errors = 0

        for html_file in html_files:
            stem = html_file.stem  # filename without extension

            # Resolve the route segment from the explicit mapping, or derive from stem
            route_segment = TEMPLATE_ROUTE_MAP.get(stem, _normalize_slug_segment(stem))
            slug = f"{prefix}/{route_segment}"

            # Validate slug — catch mismatches early so the operator can fix the map
            if not _SLUG_VALID_RE.match(slug):
                self.stdout.write(
                    self.style.ERROR(f"  SKIP  {html_file.name!r}  — invalid slug {slug!r}")
                )
                errors += 1
                continue

            title = _filename_to_title(stem)
            html_content = html_file.read_text(encoding="utf-8", errors="replace")

            try:
                page = Page.objects.get(slug=slug)
            except Page.DoesNotExist:
                page = None

            if page is not None:
                if do_update:
                    if dry_run:
                        self.stdout.write(f"  UPDATE {slug!r}  ({html_file.name})")
                    else:
                        page.html = html_content
                        page.save(update_fields=["html", "updated_at"])
                        self.stdout.write(f"  UPDATE {slug!r}  ({html_file.name})")
                    updated += 1
                else:
                    self.stdout.write(f"  SKIP   {slug!r}  — already exists (use --update to overwrite)")
                    skipped += 1
                continue

            # Create new page
            if dry_run:
                self.stdout.write(f"  CREATE {slug!r}  title={title!r}  ({html_file.name})")
            else:
                Page.objects.create(
                    title=title,
                    slug=slug,
                    html=html_content,
                    status="published",
                )
                self.stdout.write(self.style.SUCCESS(f"  CREATE {slug!r}  title={title!r}"))
            created += 1

        self.stdout.write("")
        summary = f"Done. created={created}  updated={updated}  skipped={skipped}  errors={errors}"
        if errors:
            self.stdout.write(self.style.ERROR(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
