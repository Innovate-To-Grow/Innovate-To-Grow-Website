"""Tool registry and execution for AI chat Bedrock tool-use integration."""

from .dispatch.executor import execute_tool
from .dispatch.registry import TOOL_REGISTRY

__all__ = ["TOOL_REGISTRY", "execute_tool"]
