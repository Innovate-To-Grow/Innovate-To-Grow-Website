# Shared StatusSnapshotV1 contract fixtures

These fixtures are the language-neutral contract cases for both the public
Lambda projection and the browser validator.

- `valid/*.json` files are complete API response documents and must validate
  without transformation.
- `invalid/*.json` files are compact mutation specifications. Each specification
  names a valid base document, applies the listed JSON Pointer operations in
  order, and records the validation issue that must result.

Mutation operations use this deliberately small format:

```json
{
  "description": "Human-readable purpose",
  "base": "../valid/status-v1-operational.json",
  "mutations": [
    {"op": "add", "path": "/internalError", "value": "not public"},
    {"op": "replace", "path": "/summary/availability24h/percent", "value": 101},
    {"op": "remove", "path": "/components/4"}
  ],
  "expectedIssue": "stable substring from the contract validator"
}
```

Supported operations are `add`, `replace`, and `remove`. Paths follow RFC 6901
escaping (`~0` for `~`, `~1` for `/`). Tests must enumerate every JSON file in
both directories so adding a fixture automatically adds coverage in each
implementation.
