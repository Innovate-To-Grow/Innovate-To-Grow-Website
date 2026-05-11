import json as jsonlib
import logging

from core.services.db_tools import execute_tool

logger = logging.getLogger(__name__)


def process_stream_response(response):
    content_blocks = []
    current_block = {}
    stop_reason = "end_turn"
    tool_use_input_buf = ""
    usage = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}
    for event in response.get("stream", []):
        if "contentBlockStart" in event:
            current_block, tool_use_input_buf = start_content_block(event)
        elif "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                current_block.setdefault("text", "")
                current_block["text"] += delta["text"]
                yield {"type": "text", "chunk": delta["text"]}
            elif "toolUse" in delta:
                tool_use_input_buf += delta["toolUse"].get("input", "")
        elif "contentBlockStop" in event:
            content_blocks.append(stop_content_block(current_block, tool_use_input_buf))
            current_block = {}
            tool_use_input_buf = ""
        elif "messageStop" in event:
            stop_reason = event["messageStop"].get("stopReason", "end_turn")
        elif "metadata" in event:
            data = event["metadata"].get("usage", {})
            usage = {
                "inputTokens": data.get("inputTokens", 0),
                "outputTokens": data.get("outputTokens", 0),
                "totalTokens": data.get("totalTokens", 0),
            }
    return {"content_blocks": content_blocks, "stop_reason": stop_reason, "usage": usage}


def start_content_block(event):
    start = event["contentBlockStart"].get("start", {})
    if "toolUse" in start:
        return {
            "type": "toolUse",
            "toolUseId": start["toolUse"]["toolUseId"],
            "name": start["toolUse"]["name"],
        }, ""
    return {"type": "text", "text": ""}, ""


def stop_content_block(current_block, tool_use_input_buf):
    if current_block.get("type") == "toolUse":
        try:
            parsed_input = jsonlib.loads(tool_use_input_buf) if tool_use_input_buf else {}
        except jsonlib.JSONDecodeError:
            parsed_input = {}
        return {
            "toolUse": {
                "toolUseId": current_block["toolUseId"],
                "name": current_block["name"],
                "input": parsed_input,
            }
        }
    return {"text": current_block.get("text", "")}


def stream_tool_results(content_blocks, round_num):
    for block in content_blocks:
        if "toolUse" not in block:
            continue
        tool_info = block["toolUse"]
        logger.info("Stream tool call round %d: %s", round_num, tool_info.get("name"))
        result_text = execute_tool(tool_info)
        yield (
            {
                "type": "tool_call",
                "name": tool_info.get("name", "unknown"),
                "input": tool_info.get("input", {}),
                "result_preview": result_text[:200],
            },
            {"toolResult": {"toolUseId": tool_info["toolUseId"], "content": [{"text": result_text}]}},
        )
