"""Amplify reconciliation errors."""


class AmplifyRedirectSyncError(RuntimeError):
    """Base error for edge redirect reconciliation."""


class AmplifyRedirectConfigurationError(AmplifyRedirectSyncError):
    """The deployment has not provided enough configuration to sync."""
