"""Reconcile backend-owned routing into AWS Amplify custom rules.

Deployment settings define canonical passthrough/fallback rules and the database
defines CMS redirects; each run preserves unrelated Amplify rules.

* ``rules`` — the pure rule transformation (base rules, merge).
* ``config`` — the deployment configuration snapshot a reconciliation runs with.
* ``reconcile`` — the serialized provider call that applies the merged rules.
* ``jobs`` — durable scheduling: coalescing, supersession, retries, status mirroring.
"""

from .config import AMPLIFY_CONFIGURATION_PAYLOAD_KEY, AMPLIFY_REDIRECT_JOB_KIND
from .errors import AmplifyRedirectConfigurationError, AmplifyRedirectSyncError
from .jobs import (
    get_amplify_redirect_sync_status,
    schedule_amplify_redirect_sync,
    sync_amplify_redirect_job_state,
    sync_amplify_redirects_job,
)
from .reconcile import AmplifyReconcileResult, reconcile_amplify_redirects
from .rules import amplify_source_variants, canonical_amplify_base_rules, merge_amplify_rules

__all__ = [
    "AMPLIFY_CONFIGURATION_PAYLOAD_KEY",
    "AMPLIFY_REDIRECT_JOB_KIND",
    "AmplifyRedirectConfigurationError",
    "amplify_source_variants",
    "canonical_amplify_base_rules",
    "get_amplify_redirect_sync_status",
    "merge_amplify_rules",
    "reconcile_amplify_redirects",
    "schedule_amplify_redirect_sync",
    "sync_amplify_redirect_job_state",
    "sync_amplify_redirects_job",
    "AmplifyReconcileResult",
    "AmplifyRedirectSyncError",
]
