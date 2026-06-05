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
    # --- wave-2 extension points ---
    from . import apps_cmd, completion

    completion.register(app)  # U6
    apps_cmd.register(app)  # U10
