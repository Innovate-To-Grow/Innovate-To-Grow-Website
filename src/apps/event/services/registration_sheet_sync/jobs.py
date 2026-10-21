"""Background-job handlers for an event's registration-sheet sync."""


def sync_registration_sheet_job(job) -> None:
    from apps.event.services.registration_sheet_sync import _flush_pending_sync
    from apps.event.services.registration_sheet_sync.scheduler import job_should_run

    if job_should_run(job):
        _flush_pending_sync(job.payload["event_id"], raise_errors=True, job=job)


def sync_registration_sheet_job_state(job):
    from apps.event.services.registration_sheet_sync.scheduler import mirror_job_state

    mirror_job_state(job)
