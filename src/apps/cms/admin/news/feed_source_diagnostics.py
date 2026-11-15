from django.contrib import messages

_MESSAGE_DIAGNOSTIC_MAX_ITEMS = 3


_MESSAGE_DIAGNOSTIC_MAX_LENGTH = 1200


_MESSAGE_TRUNCATION_SUFFIX = "… (truncated; see Last Sync Status or sync log for full details)"


def _bounded_diagnostic(value, *, max_length, suffix="…"):
    text = " ".join(str(value).split())
    if len(text) <= max_length:
        return text
    if len(suffix) >= max_length:
        return suffix[:max_length]
    return f"{text[: max_length - len(suffix)].rstrip()}{suffix}"


def _result_messages(result, key):
    values = result.get(key) or []
    if isinstance(values, str):
        values = [values]
    return [message for value in values if (message := " ".join(str(value).split()))]


def _diagnostic_details(values, *, prefix):
    entries = [f"{prefix}: {message}" for message in values[:_MESSAGE_DIAGNOSTIC_MAX_ITEMS]]
    omitted = len(values) - len(entries)
    if omitted:
        entries.append(f"… (+{omitted} more; see Last Sync Status or sync log for full details)")
    return _bounded_diagnostic(
        f"Details: {' | '.join(entries)}",
        max_length=_MESSAGE_DIAGNOSTIC_MAX_LENGTH,
        suffix=_MESSAGE_TRUNCATION_SUFFIX,
    )


def _show_sync_result(request, summary, result):
    errors = _result_messages(result, "errors")
    warnings = _result_messages(result, "warnings")

    if errors:
        messages.error(
            request,
            f"{summary} {len(errors)} error(s). {_diagnostic_details(errors, prefix='Error')}",
        )
    if warnings:
        messages.warning(
            request,
            f"{summary} {len(warnings)} warning(s). {_diagnostic_details(warnings, prefix='Warning')}",
        )
    if not errors and not warnings:
        messages.success(request, summary)


def _stored_diagnostics(value):
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]
