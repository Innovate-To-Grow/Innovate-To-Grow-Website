from datetime import timedelta
from hashlib import sha256
from pathlib import PurePosixPath
from uuid import UUID

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.core.services.background_jobs import PermanentJobError, TransientJobError, enqueue_job
from apps.system_intelligence.models import SystemIntelligenceExport
from apps.system_intelligence.models.export import private_export_storage

EXPORT_PREFIX = "system_intelligence_exports"
CLEANUP_JOB = "system_intelligence.delete_export"
ORPHAN_GRACE_PERIOD = timedelta(days=1)


def is_export_key(name):
    if not isinstance(name, str):
        return False
    parts = PurePosixPath(name).parts
    if not (
        len(parts) == 3
        and parts[0] == EXPORT_PREFIX
        and "\\" not in name
        and parts[-1].endswith(".xlsx")
        and name == "/".join(parts)
    ):
        return False
    try:
        return str(UUID(parts[1])) == parts[1]
    except ValueError:
        return False


def enqueue_deletion(name, *, orphan=False):
    reason = "orphan" if orphan else "deleted"
    digest = sha256(name.encode()).hexdigest()
    enqueue_job(kind=CLEANUP_JOB, dedupe_key=f"{reason}:{digest}", payload={"name": name})


@receiver(post_delete, sender=SystemIntelligenceExport)
def enqueue_export_cleanup(sender, instance, **kwargs):
    if instance.private_file:
        enqueue_deletion(instance.private_file.name)


def _export_uses_key(export, name):
    return export.private_file.name == name or (not export.private_file and export.file.name == name)


@transaction.atomic
def delete_export_job(job):
    name = job.payload.get("name")
    if not is_export_key(name):
        raise PermanentJobError("Invalid private export key.")
    export = SystemIntelligenceExport.objects.select_for_update().filter(pk=name.split("/")[1]).first()
    if export and _export_uses_key(export, name):
        return
    try:
        private_export_storage().delete(name)
    except FileNotFoundError:
        return
    except Exception as exc:
        raise TransientJobError("Private export file could not be deleted.") from exc


def iter_export_keys(storage):
    try:
        directories, _files = storage.listdir(EXPORT_PREFIX)
    except FileNotFoundError:
        return
    for directory in directories:
        try:
            _subdirectories, files = storage.listdir(f"{EXPORT_PREFIX}/{directory}")
        except FileNotFoundError:
            continue
        for filename in files:
            name = f"{EXPORT_PREFIX}/{directory}/{filename}"
            if is_export_key(name):
                yield name


def iter_private_orphans():
    storage = private_export_storage()
    cutoff = timezone.now() - ORPHAN_GRACE_PERIOD
    for name in iter_export_keys(storage):
        try:
            modified = storage.get_modified_time(name)
        except FileNotFoundError:
            continue
        if modified >= cutoff:
            continue
        export = SystemIntelligenceExport.objects.filter(pk=name.split("/")[1]).first()
        if not export or not _export_uses_key(export, name):
            yield name
