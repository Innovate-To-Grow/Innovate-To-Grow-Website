# Events Sheet Sync API

This document describes the DB-primary export API used by Google Apps Script to sync event display data into Google Sheets.

## Endpoint

- URL: `/api/events/sync/export/`
- Method: `GET`
- Auth header: `X-API-Key: <EVENTS_API_KEY>`

## Query Parameters

- `mode` (optional): `full` or `delta`
  - default: `full`
- `since` (required when `mode=delta`):
  - ISO-8601 datetime, for example: `2026-02-10T20:00:00Z`

## Response Shape

```json
{
  "meta": {
    "source": "i2g-db",
    "scope": "live_event",
    "mode": "full",
    "delta_changed": true,
    "generated_at": "2026-02-10T21:00:00Z",
    "watermark": "2026-02-10T20:55:12Z",
    "event": {
      "event_uuid": "uuid",
      "slug": "spring-expo-2026",
      "event_name": "Spring 2026 Event"
    }
  },
  "worksheets": {
    "event_basic": [],
    "event_bullets": [],
    "event_expo": [],
    "event_reception": [],
    "event_schedule": [],
    "event_track_winners": [],
    "event_special_awards": []
  }
}
```

## Delta Semantics

- `mode=full`: always returns full worksheet snapshots.
- `mode=delta`:
  - `delta_changed=false`: all worksheet arrays are empty.
  - `delta_changed=true`: full worksheet snapshots are returned.
- Watermark is based on `Event.updated_at`.

## Error Codes

- `401/403`: missing or invalid API key
- `400`: invalid query params (`mode`, `since`)
- `404`: no live event
- `200`: success

## curl Examples

Full export:

```bash
curl -sS \
  -H "X-API-Key: $EVENTS_API_KEY" \
  "https://i2g.ucmerced.edu/api/events/sync/export/?mode=full"
```

Delta export:

```bash
curl -sS \
  -H "X-API-Key: $EVENTS_API_KEY" \
  "https://i2g.ucmerced.edu/api/events/sync/export/?mode=delta&since=2026-02-10T20:00:00Z"
```

## Google Apps Script Example (Pull + Rewrite Tabs)

```javascript
function syncI2GEventSheets() {
  const apiKey = PropertiesService.getScriptProperties().getProperty("EVENTS_API_KEY");
  const lastSince = PropertiesService.getScriptProperties().getProperty("I2G_EVENT_SINCE");
  const mode = lastSince ? "delta" : "full";
  const since = lastSince || "1970-01-01T00:00:00Z";

  const url = `https://i2g.ucmerced.edu/api/events/sync/export/?mode=${mode}&since=${encodeURIComponent(since)}`;
  const response = UrlFetchApp.fetch(url, {
    method: "get",
    muteHttpExceptions: true,
    headers: { "X-API-Key": apiKey }
  });

  if (response.getResponseCode() !== 200) {
    throw new Error(`Sync failed: ${response.getResponseCode()} ${response.getContentText()}`);
  }

  const payload = JSON.parse(response.getContentText());
  if (!payload.meta.delta_changed) {
    return;
  }

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const worksheets = payload.worksheets;
  Object.keys(worksheets).forEach((name) => {
    const rows = worksheets[name];
    const sheet = ss.getSheetByName(name) || ss.insertSheet(name);
    sheet.clearContents();
    if (!rows || rows.length === 0) return;

    const headers = Object.keys(rows[0]);
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    const values = rows.map((row) => headers.map((h) => row[h]));
    sheet.getRange(2, 1, values.length, headers.length).setValues(values);
  });

  PropertiesService.getScriptProperties().setProperty("I2G_EVENT_SINCE", payload.meta.watermark);
}
```
