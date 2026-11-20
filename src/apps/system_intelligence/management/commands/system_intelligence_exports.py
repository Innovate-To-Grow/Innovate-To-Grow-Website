from collections import Counter

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from apps.system_intelligence.models import SystemIntelligenceExport
from apps.system_intelligence.services.tools.exports.cleanup import (
    enqueue_deletion,
    iter_export_keys,
    iter_private_orphans,
)
from apps.system_intelligence.services.tools.exports.migration import migrate_export


class Command(BaseCommand):
    help = "Inventory, migrate or retire System Intelligence exports, or queue private orphan cleanup."

    def add_arguments(self, parser):
        modes = parser.add_mutually_exclusive_group()
        modes.add_argument("--apply", action="store_true")
        modes.add_argument("--retire", action="store_true")
        modes.add_argument("--queue-private-orphans", action="store_true")

    def handle(self, *args, **options):
        if options["queue_private_orphans"]:
            count = 0
            for name in iter_private_orphans():
                enqueue_deletion(name, orphan=True)
                count += 1
            self.stdout.write(f"Submitted {count} private orphan(s) to the cleanup queue.")
            return
        legacy = SystemIntelligenceExport.objects.exclude(file="")
        if not (options["apply"] or options["retire"]):
            self._inventory(legacy)
            return
        counts = Counter()
        for pk in legacy.order_by("pk").values_list("pk", flat=True).iterator():
            result = migrate_export(pk, retire=options["retire"])
            counts[result] += 1
            if result not in {"unchanged", "migrated", "retired"}:
                self.stderr.write(f"{pk}: {result}")
        self.stdout.write(str(dict(sorted(counts.items()))))
        failures = set(counts) - {"unchanged", "migrated", "retired"}
        if failures:
            raise CommandError("Some exports need review. Re-run the command after resolving the reported issues.")

    def _inventory(self, legacy):
        counts = Counter()
        for name in legacy.values_list("file", flat=True).iterator():
            counts["referenced"] += 1
            if not default_storage.exists(name):
                counts["missing"] += 1
                self.stderr.write(f"Missing legacy file: {name!r}")
        for name in iter_export_keys(default_storage):
            if not legacy.filter(file=name).exists():
                counts["unreferenced"] += 1
                self.stderr.write(f"Unreferenced legacy file: {name!r}")
        self.stdout.write(str(dict(sorted(counts.items()))))
