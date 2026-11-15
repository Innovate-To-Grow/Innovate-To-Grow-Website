"""Email Monitoring → Bounced addresses: one row per address that ever bounced, and what staff may do about it.

- ``aggregate`` counts bounce reports per address (Microsoft Graph reports, Amazon SES events and "left the
  organisation" notices: ``graph_source``, ``ses_source``, ``notices``), incrementally and once each, and keeps the
  counts after the reports are purged. It changes no member, contact or subscription. ``aggregate.suggestions``
  turns counts into a text-only suggestion.
- ``listing.matching`` finds, live, the contact emails and members an address belongs to (its role: primary,
  secondary, other, unlinked contact, not a contact, ambiguous).
- ``listing`` filters, sorts and pages the list; ``listing.export`` writes it as a spreadsheet.
- ``actions.guards`` decides which action a staff member may take on an address right now, and why not;
  ``actions`` applies one (each explicit, permission-checked, re-checked on apply and audited by ``actions.audit``).

The package ``__init__`` imports nothing, so the send path can use ``apps.mail.services.suppression`` without
loading the actions.
"""
