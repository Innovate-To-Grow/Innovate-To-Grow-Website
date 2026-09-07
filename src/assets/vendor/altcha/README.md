# ALTCHA browser assets

Vendored from the installed `altcha` npm package, version **3.2.2**.

- `altcha.umd.js` is an unchanged copy of `dist/main/altcha.umd.cjs`. It includes its workers and runs as a classic script, so loading it through Django's external static storage does not require module CORS headers.
- `workers/pbkdf2.js` is retained from `dist/workers/pbkdf2.js`.
- `LICENSE.txt` and `package.json` retain the upstream license and attribution.

When upgrading, update the frontend lockfile and these assets together, then run the real-widget browser tests. Do not replace the UMD asset with the ES-module build without updating and testing the loader.
