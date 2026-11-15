"""
Controller and runtime sections of ``DELIVERY_RATES``: how Smart rate reacts, how long senders wait for a slot, the
lanes, the usage buckets behind the daily limits, provider discovery, and background-job retries.

These are app defaults (no provider documents them) unless a comment names a source.
"""

CONTROLLER = {
    # Smart rate starts at this share of the bound when it is switched on...
    "start_factor": 1.0,
    # ...or at this share while the bound is only the channel's fallback_rate (the real limit is unknown).
    "start_factor_without_limit": 0.5,
    # A throttle or pushback multiplies the factor by this, once per episode...
    "decrease_factor": 0.5,
    # ...then each recovery interval (per channel) adds this much back, up to 1...
    "recovery_step": 0.10,
    # ...and the factor never falls below this.
    "floor": 0.25,
    # Each backoff and retry delay is spread by ± this share, so processes do not retry in lockstep.
    "backoff_jitter": 0.20,
    # Longest Retry-After (seconds) taken from a provider as is; a longer one is capped to this.
    "retry_after_max_seconds": 3_600,
    # This many throttles in a row open the channel's "persistent throttling" breaker.
    "persistent_throttle_count": 8,
    # An open breaker lets one probe request through after this long, doubling up to the maximum.
    "breaker_probe_seconds": 900,
    "breaker_probe_max_seconds": 21_600,
}

WAITS = {
    # Longest a sender waits for a slot before it is deferred, by where it runs: an admin or API request...
    "inline_seconds": 10,
    # ...an inbox read in a request...
    "read_seconds": 5,
    # ...a background-job worker (must stay below jobs.stale_claim_seconds)...
    "worker_seconds": 30,
    # ...and a dedicated in-process campaign thread.
    "dedicated_seconds": 900,
    # Time one request may spend sending inline; it sizes inline batches and bounds the inline and read waits and
    # each channel's request_timeout_seconds (SES, SMS). Other provider timeouts are failure bounds that may exceed
    # it: Microsoft Graph's GRAPH_REQUEST_TIMEOUT_SECONDS (30, PR #643), the Gmail API's request_timeout_seconds
    # (15 per request; a sign-in code without a cached token needs two) and the 30 s Gmail IMAP socket timeout.
    # They only end a stuck call; the hard limit is the ALB idle timeout (AWS default 60 s, set outside this repo).
    "inline_request_budget_seconds": 25,
}

LANES = {
    # Campaigns (the bulk lane) use at most this share of the channel's rate...
    "bulk_share": 0.8,
    # ...and stop at (1 − this share) of every daily budget, so login codes and tickets keep the rest.
    "transactional_reserve": 0.10,
}

USAGE = {
    # Usage counts kept per channel identity in buckets of this many seconds (must divide one hour)...
    "bucket_seconds": 300,
    # ...for this long (must cover the rolling 24 h window plus one bucket).
    "retention_seconds": 172_800,
    # The state of an identity unused this long (a mailbox, host or number no longer in use) is deleted, unless a
    # breaker or cooldown is still active (must be at least retention_seconds, so no counted usage is lost).
    "idle_state_seconds": 2_592_000,
}

DISCOVERY = {
    # Timeout of each provider limit read (SES GetAccount, SMS DescribePhoneNumbers, ...).
    "timeout_seconds": 5,
    # After a throttle, the provider's limits are re-read at most this often.
    "min_refresh_after_throttle_seconds": 60,
}

JOBS = {
    # Background-job retry delay: this base, doubling per attempt, capped at the maximum...
    "retry_base_seconds": 15,
    "retry_max_seconds": 3_600,
    # ...for at most this many attempts by default.
    "default_max_attempts": 5,
    # A claimed job not finished within this long is recovered (run_background_worker --stale-minutes 10).
    "stale_claim_seconds": 600,
    # A job deferred by its delivery lane is due again at its slot plus up to this much, so deferred jobs spread out.
    "defer_jitter_seconds": 1,
    # The worker reads each delivery lane's gate (is the lane paced, cooling down or stopped?) at most this often.
    "gate_cache_seconds": 1,
    # Without the worker, a campaign is sent by an in-process runner: it re-reads the email configuration (picking up
    # a provider change) and recounts its progress every this many recipients.
    "runner_refresh_recipients": 10,
}
