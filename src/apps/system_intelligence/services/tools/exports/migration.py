from hashlib import sha256

from django.core.files.storage import default_storage
from django.db import transaction

from apps.system_intelligence.models import SystemIntelligenceExport
from apps.system_intelligence.models.export import private_export_storage

from .cleanup import is_export_key


def _checksum(storage, name):
    with storage.open(name, "rb") as source:
        digest = sha256()
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.digest()


def _matches(private_storage, private_name, legacy_name):
    return _checksum(default_storage, legacy_name) == _checksum(private_storage, private_name)


def _retire_copy(export, private_storage, legacy_name):
    if not export.private_file:
        return "not_migrated"
    if not private_storage.exists(export.private_file.name):
        return "missing_private"
    if default_storage.exists(legacy_name):
        if not _matches(private_storage, export.private_file.name, legacy_name):
            return "checksum_mismatch"
        default_storage.delete(legacy_name)
    export.file = ""
    export.save(update_fields=["file"])
    return "retired"


@transaction.atomic
def migrate_export(pk, *, retire=False):
    export = SystemIntelligenceExport.objects.select_for_update().filter(pk=pk).first()
    if export is None or not export.file:
        return "unchanged"
    legacy_name = export.file.name
    if not is_export_key(legacy_name) or legacy_name.split("/")[1] != str(pk):
        return "invalid_key"
    private_storage = private_export_storage()
    if retire:
        return _retire_copy(export, private_storage, legacy_name)
    private_name = export.private_file.name or legacy_name
    if not default_storage.exists(legacy_name):
        if export.private_file and private_storage.exists(private_name):
            return "unchanged"
        return "missing_legacy"
    if not private_storage.exists(private_name):
        with default_storage.open(legacy_name, "rb") as source:
            private_name = private_storage.save(private_name, source, max_length=255)
    if not _matches(private_storage, private_name, legacy_name):
        return "checksum_mismatch"
    if export.private_file.name == private_name:
        return "unchanged"
    export.private_file = private_name
    export.save(update_fields=["private_file"])
    return "migrated"
