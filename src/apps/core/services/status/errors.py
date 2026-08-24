"""Sanitized errors shared by the internal-status client modules."""

PUBLIC_ERROR_MESSAGES = {
    "unconfigured": "The infrastructure status connection is not configured.",
    "invalid_configuration": "The infrastructure status connection is configured incorrectly.",
    "credentials": "AWS task-role credentials are unavailable.",
    "permission": "The backend task role cannot read the internal status endpoint.",
    "throttled": "The internal status endpoint is temporarily throttled.",
    "timeout": "The internal status endpoint did not respond in time.",
    "upstream": "The internal status endpoint is temporarily unavailable.",
    "redirect": "The internal status endpoint returned an unexpected redirect.",
    "invalid_response": "The internal status endpoint returned an invalid response.",
    "error": "Infrastructure status could not be loaded.",
}


class StatusFetchError(RuntimeError):
    """A sanitized internal-status failure safe to expose in the admin UI."""

    def __init__(self, reason: str):
        normalized = reason if reason in PUBLIC_ERROR_MESSAGES else "error"
        self.reason = normalized
        self.public_message = PUBLIC_ERROR_MESSAGES[normalized]
        super().__init__(self.public_message)
