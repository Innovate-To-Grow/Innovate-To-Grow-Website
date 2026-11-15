"""Repository structure rules (architecture spec R001-R004, R032) and the migration guard (R024).

Run from the repository root (standard library only, Python 3.11+):

    python -m scripts.structure.checker report                  # report-only: exit 0 whatever it finds
    python -m scripts.structure.checker report --mode enforce   # exit 1 on an open finding or stale entry
    python -m scripts.structure.checker report --verbose        # list every open finding
    python -m scripts.structure.checker migrations --base <sha> --head <sha>

Limits, the unmeasured paths, the exceptions and the protected migration paths live in ``structure.toml``.
Policy: docs/architecture/code-quality.md ("Repository structure").
"""
