"""
Django management command: export_pages

Exports pages or homepages as a ZIP archive containing a manifest.json
and all referenced media files.

Usage:
    python manage.py export_pages about -o about.zip
    python manage.py export_pages --all -o all-pages.zip
    python manage.py export_pages --type homepage --all -o homepages.zip
"""

import json
import sys
import zipfile
from datetime import UTC, datetime
from io import BytesIO

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from pages.admin.content.import_export import (
    ZIP_EXPORT_VERSION,
    collect_component_files,
    serialize_homepage,
    serialize_page,
)
from pages.models import HomePage, Page


class Command(BaseCommand):
    help = "Export pages or homepages as a ZIP archive with media files."

    def add_arguments(self, parser):
        parser.add_argument(
            "slugs",
            nargs="*",
            help="Page slugs (or homepage names for --type homepage) to export. Omit with --all to export everything.",
        )
        parser.add_argument(
            "--type",
            choices=["page", "homepage"],
            default="page",
            dest="export_type",
            help='Type of content to export (default: "page").',
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="export_all",
            help="Export all pages/homepages.",
        )
        parser.add_argument(
            "--output",
            "-o",
            dest="output",
            default=None,
            help="Output file path. If omitted, writes to stdout.",
        )
        parser.add_argument(
            "--no-media",
            action="store_true",
            help="Exclude media files from the archive (manifest-only).",
        )

    def handle(self, *args, **options):
        slugs = options["slugs"]
        export_type = options["export_type"]
        export_all = options["export_all"]
        output_path = options["output"]
        no_media = options["no_media"]

        if not slugs and not export_all:
            raise CommandError("Provide page slugs or use --all to export everything.")

        # Gather objects
        if export_type == "page":
            objects = self._get_pages(slugs, export_all)
        else:
            objects = self._get_homepages(slugs, export_all)

        if not objects:
            raise CommandError("No matching objects found to export.")

        self.stderr.write(self.style.NOTICE(f"Exporting {len(objects)} {export_type}(s)..."))

        # Serialize entries and collect file paths
        entries = []
        all_file_paths = set()
        for obj in objects:
            if export_type == "page":
                entry = serialize_page(obj, include_files=True)
            else:
                entry = serialize_homepage(obj, include_files=True)
            entries.append(entry)
            if not no_media:
                all_file_paths |= collect_component_files(obj.components.all())

        # Build manifest
        manifest = {
            "export_version": ZIP_EXPORT_VERSION,
            "export_format": "zip",
            "exported_at": datetime.now(UTC).isoformat(),
            "entries": entries,
        }

        # Build ZIP
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
            zf.writestr("manifest.json", manifest_json)

            if not no_media:
                for file_path in sorted(all_file_paths):
                    archive_path = f"media/{file_path}"
                    try:
                        with default_storage.open(file_path, "rb") as f:
                            zf.writestr(archive_path, f.read())
                        self.stderr.write(f"  Packed: {archive_path}")
                    except FileNotFoundError:
                        self.stderr.write(
                            self.style.WARNING(f"  MISSING: {file_path} (referenced but not found on disk)")
                        )

        # Output
        zip_bytes = buffer.getvalue()
        if output_path:
            with open(output_path, "wb") as f:
                f.write(zip_bytes)
            self.stderr.write(self.style.SUCCESS(f"Exported to {output_path} ({len(zip_bytes)} bytes)"))
        else:
            sys.stdout.buffer.write(zip_bytes)
            self.stderr.write(self.style.SUCCESS(f"Exported {len(zip_bytes)} bytes to stdout"))

    def _get_pages(self, slugs, export_all):
        if export_all:
            return list(Page.objects.all().order_by("slug"))
        pages = list(Page.objects.filter(slug__in=slugs).order_by("slug"))
        found_slugs = {p.slug for p in pages}
        for slug in slugs:
            if slug not in found_slugs:
                self.stderr.write(self.style.WARNING(f"Page with slug '{slug}' not found, skipping."))
        return pages

    def _get_homepages(self, slugs, export_all):
        if export_all:
            return list(HomePage.objects.all().order_by("-created_at"))
        homepages = list(HomePage.objects.filter(name__in=slugs).order_by("-created_at"))
        found_names = {hp.name for hp in homepages}
        for name in slugs:
            if name not in found_names:
                self.stderr.write(self.style.WARNING(f"HomePage with name '{name}' not found, skipping."))
        return homepages
