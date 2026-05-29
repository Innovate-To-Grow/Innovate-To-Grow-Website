"""Compatibility wrapper for Bedrock tool definitions."""

from .tool_definitions.registry import TOOL_DEFINITIONS


def get_tool_definitions():
    """Return the list of tool definitions for the Bedrock Converse API."""
    return list(TOOL_DEFINITIONS)
