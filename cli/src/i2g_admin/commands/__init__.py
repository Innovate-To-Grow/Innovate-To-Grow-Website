"""Command-group registry — the single wiring point for the Typer app.

Each group module exposes ``register(app)``. Wave-2 units that add a new
top-level command append exactly one line under their numbered anchor below, so
parallel branches never edit the same line.
"""

from . import auth, meta, records


def register(app) -> None:
    auth.register(app)
    meta.register(app)
    records.register(app)
    # --- wave-2 extension points (one line each; keep on their own lines) ---
    # U6:  from . import completion; completion.register(app)
    # U10: from . import apps_cmd; apps_cmd.register(app)
