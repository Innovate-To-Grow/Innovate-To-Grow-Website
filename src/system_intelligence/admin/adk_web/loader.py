from asyncio import get_running_loop
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.db import close_old_connections
from google.adk.cli.utils.base_agent_loader import BaseAgentLoader

from core.models import AWSCredentialConfig
from system_intelligence.models import SystemIntelligenceConfig
from system_intelligence.services.adk.constants import APP_NAME
from system_intelligence.services.adk.runner import build_agent


class SystemIntelligenceAgentLoader(BaseAgentLoader):
    """Expose the Django-configured System Intelligence agent to ADK Web."""

    def load_agent(self, agent_name: str):
        if agent_name != APP_NAME:
            raise ValueError(f"Unknown System Intelligence ADK app: {agent_name}")

        if _has_running_event_loop():
            with ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(self._load_agent_sync).result()
        return self._load_agent_sync()

    def _load_agent_sync(self):
        close_old_connections()
        try:
            chat_config = SystemIntelligenceConfig.load()
            aws_config = AWSCredentialConfig.load()
            return build_agent(
                chat_config=chat_config,
                aws_config=aws_config,
                model_id=aws_config.default_model_id,
                include_temperature=False,
                mode="normal",
                include_writes=False,
                include_exports=False,
            )
        finally:
            close_old_connections()

    def list_agents(self) -> list[str]:
        return [APP_NAME]

    def list_agents_detailed(self) -> list[dict[str, Any]]:
        return [
            {
                "name": APP_NAME,
                "display_name": "System Intelligence",
                "description": "Read-only ADK Web shell for Innovate to Grow operational data.",
                "type": "LlmAgent",
            }
        ]


def _has_running_event_loop() -> bool:
    try:
        get_running_loop()
    except RuntimeError:
        return False
    return True
