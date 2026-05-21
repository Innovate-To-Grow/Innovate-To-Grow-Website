import asyncio
from unittest.mock import patch

from django.test import SimpleTestCase

from core.services.db_tools.tools import TOOL_REGISTRY
from system_intelligence.services import tools as system_intelligence_tools


class SystemIntelligenceADKToolTests(SimpleTestCase):
    def test_tool_wrapper_passes_compact_params_and_closes_connections(self):
        calls = []

        def fake_tool(params):
            calls.append(params)
            return "ok"

        with (
            patch.dict(TOOL_REGISTRY, {"search_members": fake_tool}),
            patch("system_intelligence.services.tools.close_old_connections") as close_connections,
        ):
            result = asyncio.run(system_intelligence_tools.search_members(name="Ada", email=None))

        self.assertEqual(result, {"result": "ok"})
        self.assertEqual(calls, [{"name": "Ada"}])
        self.assertEqual(close_connections.call_count, 2)

    def test_custom_query_rejects_unallowlisted_output_fields(self):
        result = TOOL_REGISTRY["run_custom_query"]({"model": "Member", "fields": ["password"], "limit": 1})
        self.assertEqual(result, "Fields error: field 'password' is not allowed for Member.")
