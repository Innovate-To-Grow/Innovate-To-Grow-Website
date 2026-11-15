"""The tool-free prompt: the system text with its grounding context, and the visitor's transcript made valid."""

_VALID_ROLES = {"user", "assistant"}


def _system_text(config, context: str) -> str:
    text = config.public_assistant_system_prompt
    if context:
        text += "\n\nCONTEXT:\n" + context
    return text


def _trimmed_messages(history, message: str) -> list[dict]:
    """Build agent input messages from history + the new user turn.

    Roles are coerced to user/assistant and blank turns dropped. The Bedrock
    Anthropic chat models behind the agent expect the transcript to begin with
    a user turn and to strictly alternate user/assistant; visitor-supplied
    history is untrusted, so we enforce both here before invoking the agent:

    - drop any leading assistant turns so the first turn is always ``user``;
    - collapse consecutive same-role turns, keeping the most recent one.

    The new user message is always appended last so the request ends on a user
    turn (merging into a trailing history ``user`` turn if present).
    """
    cleaned: list[dict] = []
    for turn in history or []:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role not in _VALID_ROLES or not content:
            continue
        cleaned.append({"role": role, "text": content})

    messages: list[dict] = []
    for turn in cleaned:
        # Skip leading assistant turns: the transcript must start with a user.
        if not messages and turn["role"] != "user":
            continue
        # Collapse consecutive same-role turns (keep the latest content).
        if messages and messages[-1]["role"] == turn["role"]:
            messages[-1] = turn
            continue
        messages.append(turn)

    # Append the new user message, alternating correctly: if the transcript
    # already ends on a user turn, replace it so we don't emit user/user.
    if messages and messages[-1]["role"] == "user":
        messages[-1] = {"role": "user", "text": message}
    else:
        messages.append({"role": "user", "text": message})

    return [{"role": t["role"], "content": t["text"]} for t in messages]
