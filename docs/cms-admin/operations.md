# Operational Admin Tasks

## Google Sheets sources

- Sheet sources define the slug, credentials, cache policy, and display mode used by the public proxy.
- Changes to active sources should be followed by a cache-clearing or verification pass.

## Events

- Event registrations, tickets, and questions are managed in the event admin.

## News and projects

- News articles and feed sources are managed in admin and synchronized with the `sync_news` workflow.
- Project imports remain tied to semester records and project import tooling.

## Common pitfalls

- Publishing a CMS page without verifying its `page_css_class` can produce a layout mismatch.
- Editing menu items without checking route compatibility can break navigation.
- Changing sheet source credentials without revalidating the proxy will surface stale or empty data.
