# Archived event page service

This small Flask service serves the preserved event pages and proxies the
allowlisted Google Sheets ranges so the API key never reaches a browser.

The production image contains only `requirements.txt`. Tests use
`requirements-dev.txt`. Both are complete Python 3.11 locks with package
hashes; edit the matching `.in` files and regenerate from this directory:

```sh
./compile-requirements.sh
```

`SHEETS_API_KEY` is required for the Sheets proxy. `/healthz` is process
liveness and never calls Google. `/readyz` validates the key plus one
uncached, three-second request for an allowlisted `A1` cell; upstream or
configuration failure returns a sanitized 503.
