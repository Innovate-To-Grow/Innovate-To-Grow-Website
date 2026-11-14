"""The checked impersonation subject: a leaf module, so ``access`` and ``auth`` can both use it without a cycle.

``access.require_subject`` is the only code that builds an ``AllowedSubject`` (after the allow-list check), and
``auth`` refuses anything else before any key read or token request. This guards against accidental misuse only:
any code could import ``_ISSUED``. The real control is that the allow-list check runs first, which the tests prove.
"""

from dataclasses import dataclass, field

from apps.core.models.base.service_credentials.gmail_api import normalize_subject

_ISSUED = object()


@dataclass(frozen=True)
class AllowedSubject:
    """A Workspace account the allow-list lets the site impersonate (and send From)."""

    address: str
    _issued: object = field(default=None, repr=False, compare=False)


def issue(address: str) -> AllowedSubject:
    """For ``access.require_subject`` only, once *address* passed the allow-list check."""
    return AllowedSubject(normalize_subject(address), _ISSUED)


def require_issued(subject) -> AllowedSubject:
    if not isinstance(subject, AllowedSubject) or subject._issued is not _ISSUED:
        raise TypeError("Gmail API tokens are requested only for a subject that passed the allow-list check.")
    return subject
