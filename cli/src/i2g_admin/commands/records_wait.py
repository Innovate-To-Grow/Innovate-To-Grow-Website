"""``records wait`` — poll the list endpoint until a record reaches a state.

Mirrors ``aws <service> wait ...``: repeatedly query
``GET /admin-api/records/<app>/<model>/`` with the given ``--filter`` params
until some returned record's ``--until`` field matches the expected value, or a
timeout elapses. Exits 0 on success, 1 (via :class:`CliError`) on timeout.
"""

import time

import typer

from .. import runtime
from ..errors import CliError
from .query_params import filter_params

DEFAULT_TIMEOUT = 300.0
DEFAULT_INTERVAL = 5.0

# Natural / JSON spellings for booleans and null, so ``--until is_published=true``
# matches a record whose value is the Python bool ``True`` (str(True) == "True",
# not "true"). Comparison is case-insensitive.
_BOOL_WORDS = {"true": True, "false": False}
# Spellings for a null field. The empty string is deliberately NOT a member: an
# empty ``--until field=`` waits for a genuine empty string (via the str fallback
# below), never None, so null and "" are never conflated. Use ``field=null`` for None.
_NULL_WORDS = {"null", "none"}


def register(records_app: typer.Typer) -> None:
    records_app.command("wait")(wait_fn)


def _parse_until(until: str) -> tuple[str, str]:
    """Split ``field=value`` into ``(field, value)``; the value may contain ``=``."""
    if "=" not in until:
        raise CliError(f"--until must be 'field=value' (got {until!r}).")
    field, value = until.split("=", 1)
    field = field.strip()
    if not field:
        raise CliError(f"--until must be 'field=value' (got {until!r}).")
    return field, value


def _value_matches(value, expected: str) -> bool:
    """Compare a record value against the ``--until`` expected string.

    Booleans accept natural/JSON spellings (``true``/``false``, case-insensitive)
    as well as the Python repr (``True``/``False``); ``None`` accepts ``null`` /
    ``none`` (case-insensitive). An empty expected value (``field=``) matches a
    genuine empty string, not ``None`` — use ``field=null`` to wait for null — so
    the two are never conflated. Everything else falls back to
    ``str(value) == expected`` so numbers and strings keep their natural spelling.
    """
    if isinstance(value, bool):
        word = _BOOL_WORDS.get(expected.strip().lower())
        return word is value if word is not None else str(value) == expected
    if value is None:
        return expected.strip().lower() in _NULL_WORDS
    return str(value) == expected


def _matches(results, field: str, expected: str):
    """Return the first record whose ``field`` matches ``expected``, else None."""
    for record in results or []:
        if not isinstance(record, dict):
            continue
        if field in record and _value_matches(record[field], expected):
            return record
    return None


def _poll_until(action, predicate, *, timeout: float, interval: float):
    """Call ``action`` until ``predicate`` returns a truthy value or time runs out.

    The deadline is checked before sleeping so the final attempt is not wasted on
    a trailing sleep, and the interval never overshoots the remaining budget.
    """
    deadline = time.monotonic() + timeout
    while True:
        match = predicate(action())
        if match is not None:
            return match
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        # Clamp to a non-negative delay so an odd --interval can never make
        # time.sleep raise ValueError; never overshoot the remaining budget.
        time.sleep(max(0.0, min(interval, remaining)))


def wait_fn(
    app_label: str,
    model_name: str,
    until: str = typer.Option(..., "--until", help="field=value to wait for (string compare)."),
    filter_: list[str] = typer.Option(None, "--filter", help="key=value (repeatable)."),
    timeout: float = typer.Option(DEFAULT_TIMEOUT, "--timeout", help="Max seconds to wait."),
    interval: float = typer.Option(DEFAULT_INTERVAL, "--interval", help="Seconds between polls."),
    as_json: bool = typer.Option(False, "--json", help="Emit the matching record as JSON."),
) -> None:
    """Poll a model's list endpoint until a record reaches the desired state."""
    field, expected = _parse_until(until)
    params = filter_params(filter_)
    path = f"/admin-api/records/{app_label}/{model_name}/"

    def run():
        def fetch():
            payload = runtime._client().get(path, params=params)
            results = payload.get("results") if isinstance(payload, dict) else None
            return results or []

        match = _poll_until(
            fetch,
            lambda results: _matches(results, field, expected),
            timeout=timeout,
            interval=interval,
        )
        if match is None:
            raise CliError(f"Timed out after {timeout:g}s waiting for {field}={expected}.")
        # The success notice goes to stderr so it never pollutes the rendered
        # record on stdout; the record itself is returned unconditionally so the
        # global --output/--query (and the --json alias) can format it.
        typer.secho(f"Condition met: {field}={expected}.", fg=typer.colors.GREEN, err=True)
        return match

    runtime._execute(run, as_json=as_json)
