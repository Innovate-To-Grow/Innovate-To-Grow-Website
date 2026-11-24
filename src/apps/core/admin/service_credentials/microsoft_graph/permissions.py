"""The Graph permission check in the admin: the "Check permissions" button of a Graph config and its card.

A run requests a fresh token and, when the Message Trace role is in it or Message Trace is on, makes one read-only
trace request; it sends no mail and needs no deny mailbox. It is a POST (CSRF-protected by the admin site, like the
access check) with a 30-second cooldown per config, and redirects back to the card. It never records a
``MicrosoftGraphAccessCheck``, so it cannot change the go-live evidence.
"""

import datetime
import math

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone

from apps.core.models import MicrosoftGraphPermissionCheck
from apps.core.models.base.service_credentials.microsoft_graph import MESSAGE_TRACE_ROLE
from apps.core.services.email.graph.access_check import permissions
from apps.core.services.email.graph.credential.expiry import local_time_text

from .panel import BADGE_CLASSES, CHANGE_URL_NAME, URL_NAME_PREFIX

PERMISSIONS_URL_NAME = f"{URL_NAME_PREFIX}_check_permissions"
CARD_ANCHOR = "graph-permissions"
COOLDOWN = datetime.timedelta(seconds=30)
NOT_ALLOWED = "You do not have permission to check the Microsoft Graph permissions."
COOLING_DOWN = "The permissions were checked moments ago; wait {seconds} seconds before checking again."
Trace = MicrosoftGraphPermissionCheck.TraceResult
TRACE_TONES = {Trace.AVAILABLE: "success", Trace.NOT_GRANTED: "warning", Trace.THROTTLED: "warning"}
TRACE_SETUP_STEPS = (
    "InfoSec reviews the tenant-wide permission; record its reference in the InfoSec Exception Reference field.",
    f"OIT grants the {MESSAGE_TRACE_ROLE} application permission with admin consent.",
    f"OIT creates the service principal for the Message Trace app ({permissions.TRACE_APP_ID}); this can take hours.",
    "Check permissions again until Message Trace shows Available, then switch Message Trace Delivery Status on.",
)
NO_CHECK_YET = "no permission check has been run yet: run Check permissions first."
TOGGLE_WARNING = (
    "Message Trace Delivery Status is on, but {problem} The sync makes no trace request until the token carries "
    f"{MESSAGE_TRACE_ROLE}; sending is not affected."
)


class GraphPermissionCheckViewMixin:
    """The "Check permissions" POST for ``MicrosoftGraphProviderConfigAdmin`` (with ``GraphCertificateViewsMixin``)."""

    def get_permission_check_urls(self):
        view = self.admin_site.admin_view(self.check_permissions_view)
        return [path("<path:object_id>/check-permissions/", view, name=PERMISSIONS_URL_NAME)]

    def check_permissions_view(self, request, object_id):
        if not self.has_change_permission(request):
            raise PermissionDenied(NOT_ALLOWED)
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        config = self._config(request, object_id)
        back = f"{reverse(f'admin:{CHANGE_URL_NAME}', args=[config.pk])}#{CARD_ANCHOR}"
        wait = cooldown_seconds(config)
        if wait:
            messages.warning(request, COOLING_DOWN.format(seconds=wait))
            return HttpResponseRedirect(back)
        report, _check = permissions.run_and_record(config, checked_by=request.user)
        level = messages.SUCCESS if report.token_ok and not report.warning else messages.WARNING
        if not report.token_ok:
            level = messages.ERROR
        messages.add_message(request, level, " ".join(filter(None, (report.summary(), report.warning))))
        return HttpResponseRedirect(back)


def cooldown_seconds(config, *, now=None) -> int:
    """Seconds until *config*'s permissions may be checked again (0: now)."""
    latest = config.permission_checks.order_by("-created_at").values_list("created_at", flat=True).first()
    if latest is None:
        return 0
    left = (latest + COOLDOWN - (now or timezone.now())).total_seconds()
    return math.ceil(left) if left > 0 else 0


def permissions_card(config) -> dict:
    """Template context for ``permissions_card.html``: the latest permission check of *config* and its control."""
    card = {
        "caveat": permissions.CAVEAT,
        "anchor": CARD_ANCHOR,
        "check_url": reverse(f"admin:{PERMISSIONS_URL_NAME}", args=[config.pk]),
    }
    check = config.permission_checks.order_by("-created_at").first()
    if check is None:
        return card
    current = config.current_certificate
    extra = set(check.extra_roles or ())
    beyond_tone = "warning" if config.permission_exception_reference else "danger"
    tone = TRACE_TONES.get(check.trace_result, "danger")
    card.update(
        check=check,
        checked=local_time_text(check.created_at),
        for_current=current is not None and current.sha1_thumbprint == check.certificate_sha1,
        roles=[
            {
                "name": role,
                "approved": role not in extra,
                "classes": BADGE_CLASSES[beyond_tone if role in extra else "success"],
            }
            for role in check.granted_roles or ()
        ],
        capabilities=permissions.capabilities(check.granted_roles),
        trace_classes=BADGE_CLASSES[tone],
        trace_steps=TRACE_SETUP_STEPS if check.token_ok and check.trace_result != Trace.AVAILABLE else (),
        warning=permissions.RECORD_REFERENCE_FIRST if extra and not config.permission_exception_reference else "",
    )
    return card


def trace_toggle_warning(config) -> str:
    """Why switching Message Trace on will not work yet, from the latest permission check; "" when it should."""
    check = config.permission_checks.order_by("-created_at").first()
    if check is None:
        problem = NO_CHECK_YET
    elif MESSAGE_TRACE_ROLE not in (check.granted_roles or ()):
        problem = f"the latest permission check ({local_time_text(check.created_at)}) found no {MESSAGE_TRACE_ROLE}."
    else:
        return ""
    return TOGGLE_WARNING.format(problem=problem)
