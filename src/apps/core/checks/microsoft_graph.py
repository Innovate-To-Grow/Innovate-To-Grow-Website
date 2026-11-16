"""The Microsoft Graph permission names a deployment configures must be real Graph permissions."""

from django.conf import settings
from django.core.checks import Error, Tags, register

from ..utils.security import is_graph_permission


def _graph_errors() -> list[Error]:
    errors = []
    roles = getattr(settings, "GRAPH_APPROVED_APPLICATION_ROLES", None)
    if not isinstance(roles, list | tuple) or not roles or not all(is_graph_permission(role) for role in roles):
        errors.append(
            Error(
                "GRAPH_APPROVED_APPLICATION_ROLES must be a non-empty list of Graph permission names.",
                hint='For example ("Mail.Send", "Mail.ReadWrite", "Mail.Read"): the application permissions OIT granted.',
                id="core.E006",
            )
        )
    if not isinstance(getattr(settings, "GRAPH_REQUIRE_ACCESS_EVIDENCE", None), bool):
        errors.append(Error("GRAPH_REQUIRE_ACCESS_EVIDENCE must be True or False.", id="core.E007"))
    return errors


@register(Tags.security)
def check_microsoft_graph(app_configs=None, **kwargs):
    return _graph_errors()
