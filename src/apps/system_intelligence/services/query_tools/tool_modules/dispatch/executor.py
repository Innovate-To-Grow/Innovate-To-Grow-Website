"""Execute a tool call from Bedrock and return the result string."""

import logging

from django.core.exceptions import PermissionDenied

from apps.core.utils.access import user_can_access_app

from .registry import TOOL_REGISTRY

logger = logging.getLogger("apps.system_intelligence.services.query_tools.tool_modules.executor")


def execute_tool(tool_use, *, user=None):
    """Execute a tool call from Bedrock and return the result string.

    Parameters
    ----------
    tool_use : dict
        A Bedrock ``toolUse`` block with ``name``, ``toolUseId``, and ``input``.

    Returns
    -------
    str
        The tool result text.
    """
    name = tool_use.get("name", "")
    params = tool_use.get("input", {})

    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return f"Unknown tool: {name}"

    try:
        from apps.system_intelligence.services.actions.engine.tool_access import TOOL_DENIED, authorize_tool

        if not user_can_access_app(user, "system_intelligence"):
            return TOOL_DENIED
        authorize_tool(name, params, user=user)
        result = fn(params)
        logger.info("Tool %s executed successfully (%d chars)", name, len(result))
        return result
    except PermissionDenied:
        return TOOL_DENIED
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return f"Tool error: {exc}"
