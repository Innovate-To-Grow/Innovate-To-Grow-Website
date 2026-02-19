"""
Django management command: import_pages

Imports pages or homepages from a ZIP archive containing a manifest.json
and (optionally) media files.

Usage:
    python manage.py import_pages export.zip
    python manage.py import_pages export.zip --dry-run
    python manage.py import_pages export.zip --no-media
"""

import json
import zipfile

from django.core.management.base import BaseCommand, CommandError

from pages.admin.import_export import deserialize_homepage, deserialize_page


class Command(BaseCommand):
    help = "Import pages or homepages from a ZIP archive with media files."

    def add_arguments(self, parser):
        parser.add_argument(
            "zipfile",
            help="Path to the ZIP archive to import.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the archive and report what would be imported without making changes.",
        )
        parser.add_argument(
            "--no-media",
            action="store_true",
            help="Skip media file restoration (import text data only).",
        )

    def handle(self, *args, **options):
        zip_path = options["zipfile"]
        dry_run = options["dry_run"]
        no_media = options["no_media"]

        try:
            zf = zipfile.ZipFile(zip_path, "r")
        except (zipfile.BadZipFile, FileNotFoundError, OSError) as e:
            raise CommandError(f"Cannot open ZIP file: {e}")

        with zf:
            # Read manifest
            try:
                manifest_bytes = zf.read("manifest.json")
            except KeyError:
                raise CommandError("ZIP archive missing 'manifest.json'.")

            try:
                manifest = json.loads(manifest_bytes)
            except json.JSONDecodeError as e:
                raise CommandError(f"Invalid manifest.json: {e}")

            entries = manifest.get("entries", [])

            # Backward compatibility: if no "entries" key, treat as single entry
            if not entries and manifest.get("export_type"):
                entries = [manifest]

            if not entries:
                raise CommandError("manifest.json contains no entries to import.")

            export_version = manifest.get("export_version", "unknown")
            self.stdout.write(
                self.style.NOTICE(
                    f"Archive: version={export_version}, entries={len(entries)}, "
                    f"files={len(zf.namelist())}"
                )
            )

            if dry_run:
                self._dry_run_report(entries)
                return

            # Build file_map: archive path -> raw bytes
            file_map = None
            if not no_media:
                file_map = {}
                for name in zf.namelist():
                    if name.startswith("media/") and not name.endswith("/"):
                        file_map[name] = zf.read(name)

            # Import each entry
            all_warnings = []
            imported_pages = 0
            imported_homepages = 0

            for entry in entries:
                export_type = entry.get("export_type")

                if export_type == "page":
                    try:
                        page, warnings = deserialize_page(entry, file_map=file_map)
                        all_warnings.extend(warnings)
                        imported_pages += 1
                        self.stdout.write(f"  Imported page: {page.slug}")
                    except Exception as e:
                        all_warnings.append(f"Error importing page: {e}")
                        self.stderr.write(self.style.ERROR(f"  Failed to import page: {e}"))

                elif export_type == "homepage":
                    try:
                        homepage, warnings = deserialize_homepage(entry, file_map=file_map)
                        all_warnings.extend(warnings)
                        imported_homepages += 1
                        self.stdout.write(f"  Imported homepage: {homepage.name}")
                    except Exception as e:
                        all_warnings.append(f"Error importing homepage: {e}")
                        self.stderr.write(
                            self.style.ERROR(f"  Failed to import homepage: {e}")
                        )

                else:
                    msg = f"Skipped entry with unknown export_type='{export_type}'."
                    all_warnings.append(msg)
                    self.stderr.write(self.style.WARNING(f"  {msg}"))

            # Summary
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Import complete: {imported_pages} page(s), "
                    f"{imported_homepages} homepage(s)"
                )
            )
            if all_warnings:
                self.stdout.write(self.style.WARNING("Warnings:"))
                for w in all_warnings:
                    self.stdout.write(f"  - {w}")

    def _dry_run_report(self, entries):
        """Report what would be imported without making changes."""
        self.stdout.write(self.style.NOTICE("DRY RUN - no changes will be made\n"))
        for i, entry in enumerate(entries, 1):
            export_type = entry.get("export_type", "unknown")
            if export_type == "page":
                slug = entry.get("page", {}).get("slug", "???")
                comp_count = len(entry.get("components", []))
                self.stdout.write(f"  [{i}] Page: slug='{slug}', components={comp_count}")
            elif export_type == "homepage":
                name = entry.get("homepage", {}).get("name", "???")
                comp_count = len(entry.get("components", []))
                self.stdout.write(f"  [{i}] HomePage: name='{name}', components={comp_count}")
            else:
                self.stdout.write(f"  [{i}] Unknown type: '{export_type}' (will be skipped)")
