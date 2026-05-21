from typing import Any

from asgiref.sync import sync_to_async

from core.services.db_tools import TOOL_REGISTRY


def compact(params: dict[str, Any]) -> dict[str, Any]:
    """Drop unset optional values before passing params to legacy tool functions."""
    return {key: value for key, value in params.items() if value is not None}


def close_connections() -> None:
    import system_intelligence.services.tools as package

    package.close_old_connections()


def run_tool(name: str, params: dict[str, Any]) -> dict[str, str]:
    close_connections()
    try:
        return {"result": TOOL_REGISTRY[name](compact(params))}
    finally:
        close_connections()


async def run_tool_async(name: str, params: dict[str, Any]) -> dict[str, str]:
    return await sync_to_async(run_tool, thread_sensitive=True)(name, params)


def run_action_service(func, *args, **kwargs) -> dict[str, Any]:
    close_connections()
    try:
        result = func(*args, **kwargs)
        return result if isinstance(result, dict) else {"result": result}
    except Exception as exc:  # noqa: BLE001 - return tool errors to the model as tool output.
        return {"result": f"Tool error: {exc}"}
    finally:
        close_connections()


async def run_action_service_async(func, *args, **kwargs) -> dict[str, Any]:
    return await sync_to_async(run_action_service, thread_sensitive=True)(func, *args, **kwargs)
