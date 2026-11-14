"""Conservative token estimates for budgeting a call before it is made, or when the provider reports no usage."""

import math

from .prompt import _system_text, _trimmed_messages

_ENVELOPE_TOKENS_PER_MESSAGE = 8
_SYSTEM_ENVELOPE_TOKENS = 8


def _estimate_text_tokens(text: str) -> int:
    """Return a deliberately conservative tokenizer-independent estimate.

    A four-ASCII-characters-per-token approximation is useful for ordinary
    English, but it materially undercounts CJK and emoji because ``len`` counts
    Unicode code points rather than their UTF-8 representation. Bedrock can use
    several model families and does not expose a local tokenizer, so charge one
    token for every non-ASCII UTF-8 byte while retaining the established 4:1
    estimate for ASCII. This intentionally favors enforcing the public quota
    over accepting a token-dense request that was underestimated.
    """
    if not text:
        return 0
    ascii_chars = sum(character.isascii() for character in text)
    utf8_bytes = len(text.encode("utf-8", errors="surrogatepass"))
    non_ascii_bytes = utf8_bytes - ascii_chars
    return math.ceil(ascii_chars / 4) + non_ascii_bytes


def _estimate_input_tokens(system_text: str, messages: list[dict]) -> int:
    return (
        _estimate_text_tokens(system_text)
        + _SYSTEM_ENVELOPE_TOKENS
        + sum(_estimate_text_tokens(turn["content"]) + _ENVELOPE_TOKENS_PER_MESSAGE for turn in messages)
    )


def estimate_prompt_input_tokens(*, system_text: str, prompt: str) -> int:
    """Conservative input estimate for a tool-free call with one user prompt.

    Shared with the past-project AI search so it can reserve its budget before
    the model call, using the same estimator as the public chat.
    """
    return _estimate_input_tokens(system_text, [{"role": "user", "content": prompt}])


def _estimate_usage(system_text: str, messages: list[dict], reply_text: str) -> dict:
    """Conservative token estimate when Bedrock omits a usage block.

    The input estimate covers the system prompt AND every message turn actually
    sent (history + the new user message), so the per-actor and global
    budgets are not under-charged when prior turns are present.
    """
    output_tokens = _estimate_text_tokens(reply_text)
    input_tokens = _estimate_input_tokens(system_text, messages)
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
    }


def estimate_public_input_tokens(*, message, history, config, context: str) -> int:
    """Conservatively estimate the exact tool-free input assembled below."""
    messages = _trimmed_messages(history, message)
    return _estimate_input_tokens(_system_text(config, context), messages)
