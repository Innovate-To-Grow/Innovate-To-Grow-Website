# Python dependency locks

The backend runtime and CI target Python 3.11.

- `base.txt`, `production.txt`, and `local.txt` are the human-edited source
  constraints.
- `production.lock.txt` is the hash-checked runtime closure installed by the
  Docker image.
- `local.lock.txt` adds development and CI tools.
- `lock-tools.txt` pins the lock generator.

Regenerate locks from `src/` with Python 3.11:

```sh
./scripts/compile-requirements.sh
```

Commit source and lock changes together. CI verifies that both locks install
with `--require-hashes`.
