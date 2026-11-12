"""Email Monitoring → Bounced addresses: one row per address that ever bounced, and what staff may do about it.

- ``aggregate`` counts bounce reports per address (Microsoft Graph reports and Amazon SES events), incrementally and
  once each, and keeps the counts after the reports are purged. It changes no member, contact or subscription.
- ``matching`` finds, live, the contact emails and members an address belongs to (its role: primary, secondary,
  other, unlinked contact, not a contact, ambiguous).
- ``suggestions`` turns counts into a text-only suggestion.
- ``listing`` filters, sorts and pages the list; ``export`` writes it as a spreadsheet.
- ``guards`` decides which action a staff member may take on an address right now, and why not;
  ``actions`` applies one (each explicit, permission-checked, re-checked on apply and audited by ``audit``).

The package ``__init__`` imports nothing, so the send path can use ``apps.mail.services.suppression`` without
loading the actions.
"""
