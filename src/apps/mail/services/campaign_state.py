def campaign_state(*, total: int, sent: int, failed: int, active: int = 0) -> str:
    """Derive the campaign state from mutually exclusive delivery counts."""
    if active:
        return "queued" if active == total and sent == 0 and failed == 0 else "sending"
    if total == 0 or sent == total:
        return "sent"
    if sent:
        return "partial"
    return "failed"
