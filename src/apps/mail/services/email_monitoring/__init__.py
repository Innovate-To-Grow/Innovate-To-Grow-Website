"""The Email Monitoring dashboard (Mail → Delivery Operations): the queries behind its pages.

The data comes from the email telemetry and the bounce processor in ``apps.core.services.email``: ``scope`` (time
range and provider), ``overview`` (headline figures by level), ``charts`` (series and breakdowns), ``log`` (the
email log and bounce list), ``detail`` (one email's history), ``campaigns`` (per-campaign monitoring) and ``health``
(the monitoring's own state). Nothing here writes, and nothing contacts Microsoft.
"""
