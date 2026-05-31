class CliError(Exception):
    """Base class for expected, user-facing CLI errors."""


class AuthError(CliError):
    """Raised when authentication is missing, expired, or fails."""


class ApiError(CliError):
    """Raised when the admin API returns an error response."""

    def __init__(self, status_code, message, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
