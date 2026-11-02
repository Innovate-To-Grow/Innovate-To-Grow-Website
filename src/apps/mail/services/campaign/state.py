def campaign_state(*, total: int, sent: int, failed: int, active: int = 0, paused: int = 0) -> str:
    """Derive the campaign state from mutually exclusive delivery counts.

    Recipients the delivery limits paused leave a finished campaign partial until they are resumed.
    """
    if active:
        return "queued" if active == total and sent == 0 and failed == 0 else "sending"
    if paused:
        return "partial"
    if total == 0 or sent == total:
        return "sent"
    if sent:
        return "partial"
    return "failed"
