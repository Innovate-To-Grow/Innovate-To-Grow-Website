"""Operator-facing delivery error text that never carries exception internals.

Never store ``str(exc)`` (or anything derived from an exception's message) in a
campaign or recipient-log ``error_message``: the admin renders those fields and
the status-polling JSON echoes them, which is what code-scanning alert #603
(py/stack-trace-exposure) flagged.
"""

UNEXPECTED_DELIVERY_ERROR = "Unexpected error while preparing or sending this message; see server logs for details."


def unexpected_delivery_error_message(exc: BaseException) -> str:
    """Describe an unhandled send-loop exception for ``error_message`` storage.

    Recipient/campaign ``error_message`` values are shown to staff in the admin
    (send-status polling, change pages, inlines). Exception text can carry
    hostnames, credentials in URLs, or file paths, so only the exception class
    name is kept; the full traceback stays in the server log written by the
    caller's ``logger.exception``.
    """
    return f"{UNEXPECTED_DELIVERY_ERROR} ({type(exc).__name__})"
