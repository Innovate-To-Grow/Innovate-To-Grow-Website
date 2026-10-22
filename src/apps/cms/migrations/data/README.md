# Frozen migration data

`stylesheets.json` is the fixture the `cms.StyleSheet` migrations read: 0004 loads it, and 0016–0018,
0021, 0022, 0024 and 0025 re-sync rows from it. Those migrations still run on every new database, so
the file must stay exactly as it is, even though the `StyleSheet` model itself was deleted in 0030.

It is **not** the site's CSS. All of the site's CSS ships with the frontend in `pages/src` (see
`docs/cms-admin/css-contract.md`). `tests/models/test_migration_data_frozen.py` fails on any change
to this file.
