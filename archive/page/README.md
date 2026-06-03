# Innovate To Grow — archived event pages

A static archive of the legacy I2G event pages. There is **no server** — these
are plain HTML files plus a `static/` asset folder, hostable on any static host
(S3/CloudFront, GitHub Pages, `python -m http.server`, …).

## Pages

One HTML file per past event, e.g. `2025-fall-event.html`, `2024-spring-event.html`.
Open them directly or serve the folder:

```bash
python -m http.server 8000   # then visit http://localhost:8000/2025-fall-event.html
```

## Google Sheets API key

Each page fetches its tables from the Google Sheets API **client-side**, reading
the key from `window.SHEETS_API_KEY`. That global is defined in
`static/config.js`, which is **gitignored** so the key never lives in source.

To run/deploy:

```bash
cp static/config.example.js static/config.js   # then paste the real key in
```

The key is a client-side key — it is exposed to browsers by design. Protect it
in the Google Cloud console by restricting it to your HTTP referrer(s) and to
the Google Sheets API only.

## Tests

A small offline smoke suite checks the built HTML (no leftover templating, the
key is wired via `config.js` and never inlined, referenced assets exist):

```bash
pip install -r requirements.txt
pytest
```
