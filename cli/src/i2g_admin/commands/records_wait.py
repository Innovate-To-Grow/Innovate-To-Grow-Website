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

DEFAULT_TIMEOUT = 300.0
DEFAULT_INTERVAL = 5.0


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


def _matches(results, field: str, expected: str):
    """Return the first record whose ``field`` string-equals ``expected``, else None."""
    for record in results or []:
        if not isinstance(record, dict):
            continue
        if field in record and str(record[field]) == expected:
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
    params = [("filter", item) for item in filter_ or []]
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
        if as_json:
            return match
        typer.secho(f"Condition met: {field}={expected}.", fg=typer.colors.GREEN, err=True)
        return None

    runtime._execute(run, as_json=as_json)
