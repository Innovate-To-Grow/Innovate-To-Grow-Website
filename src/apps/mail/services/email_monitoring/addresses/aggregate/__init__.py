"""Keeping the bounced-address counts current: each source is read from its stored cursor, one bounded batch per
transaction, and the cursor moves with the counts, so every report is counted exactly once.

A run holds the source's state row (``select_for_update``) for each batch, so two runs never count the same rows; a
page load does not wait for it (``wait=False`` skips a source another run holds). Rows newer than
``EMAIL_MONITORING["address_settle_seconds"]`` wait for the next run: a report saved by a transaction that commits
late can then never fall behind the cursor.

It runs when the Bounced addresses page loads (a bounded batch) and in the background worker's hourly maintenance,
before the email telemetry retention purge, so counts are complete before reports are deleted. Counting only writes
``BouncedAddress`` rows and their campaign rows: never a member, a contact email or a subscription. The sources are
Microsoft Graph bounce reports (``graph``), Amazon SES events (``ses``) and the helpdesk's left-the-organisation
notices that answer the site's mail (``inbound``, see ``notices``).

Before each Graph batch, the reports saved without a category (by the previous release while a deploy rolled out)
are classified. ``mail.0026`` parks the Graph cursor (``PARKED``, far in the future) when Graph reports had been
counted before categories existed: the previous release, still running while the deploy rolls out, then counts no
Graph report, and the first count by this release starts the Graph counts again from the stored reports, so every
address gets its category counts (recorded like a rebuild). **Rebuild counts** classifies every stored report again
with the current rules first, so a change to the rules reaches the reports and the counts; it leaves the
left-the-organisation notices counted (they are never classified again, and the inbound queue keeps only 90 days).
"""

from .counting import SOURCES, count_batch, pending, run
from .links import graph_counts_agree, park_graph, rebuild, refresh_all
from .state import (
    COUNTED_FIELDS,
    GRAPH,
    GRAPH_COUNT_FIELDS,
    INBOUND,
    LINKS,
    PARKED,
    PARKED_ID,
    REBUILT_COUNT_FIELDS,
    SES,
    RunResult,
    finish,
)
