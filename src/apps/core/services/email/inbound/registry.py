"""Consumers of the inbound mail queue: apps register a background job kind, ``core`` queues it by name.

An app that turns inbound mail into something (the helpdesk makes tickets) calls ``register_inbound_consumer`` from
its ``AppConfig.ready()`` with the job kind that drains ``InboundMessage`` rows, and optionally the dotted path of a
zero-argument callable saying whether it is switched on. After a scan records new rows, ``core`` queues each active
consumer's job by name: the same "the app registers, core calls back by name" pattern as job kinds and
``CSP_FRAME_HOST_PROVIDERS``, so ``core`` imports no business app.

While no consumer is registered nothing is recorded: rows nobody drains would only pile up.
"""

import logging
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InboundConsumer:
    job_kind: str
    active: str | None = None


_CONSUMERS: dict[str, InboundConsumer] = {}


def register_inbound_consumer(job_kind: str, *, active: str | None = None) -> None:
    """Register the job kind that drains the inbound queue; ``active`` is the dotted path of a zero-argument
    callable (true while the consumer is switched on). Registering again is allowed only with identical values."""
    if not job_kind:
        raise ImproperlyConfigured("An inbound mail consumer needs a background job kind.")
    entry = InboundConsumer(job_kind, active)
    existing = _CONSUMERS.get(job_kind)
    if existing is not None and existing != entry:
        raise ImproperlyConfigured(f"Inbound mail consumer {job_kind!r} is already registered differently.")
    _CONSUMERS[job_kind] = entry


def registered_consumers() -> dict[str, InboundConsumer]:
    return dict(_CONSUMERS)


def _is_active(consumer: InboundConsumer) -> bool:
    if consumer.active is None:
        return True
    try:
        return bool(import_string(consumer.active)())
    except Exception:  # noqa: BLE001 - a broken switch must never stop the scan; the consumer is treated as off.
        logger.exception("Could not tell whether inbound mail consumer %s is on", consumer.job_kind)
        return False


def active_consumer_kinds() -> list[str]:
    """The job kinds of the consumers that are switched on, in registration order."""
    return [kind for kind, consumer in _CONSUMERS.items() if _is_active(consumer)]
