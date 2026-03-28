# Display Proxy

## Configuration

- `GoogleSheetSource` defines the slug, credentials, and display mode.
- Authentication may use service-account JSON or an API key depending on the source.
- Cached responses are keyed by slug and invalidated by page signal handlers.

## Runtime behavior

- `GET /sheets/<slug>/` serves the configured display payload.
- Fresh cache hits return immediately.
- Stale cache hits return cached content and refresh in the background.
- Cold misses fetch from Google Sheets synchronously.

## Response shape

- The response depends on the configured display mode.
- Event pages, schedules, archive pages, and project pages each expect a stable frontend-specific shape.
