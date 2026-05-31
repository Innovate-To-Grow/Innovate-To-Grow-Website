import json as jsonlib

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def emit(data, *, as_json: bool) -> None:
    if as_json:
        typer.echo(jsonlib.dumps(data, indent=2, default=str))
        return
    _render(data)


def _render(data) -> None:
    if isinstance(data, list):
        _render_list(data)
    elif isinstance(data, dict):
        _render_dict(data)
    else:
        console.print(str(data))


def _render_list(rows) -> None:
    if not rows:
        console.print("(no results)")
        return
    if all(isinstance(row, dict) for row in rows):
        columns = list({key for row in rows for key in row})
        table = Table(*columns)
        for row in rows:
            table.add_row(*[str(row.get(column, "")) for column in columns])
        console.print(table)
        return
    for row in rows:
        console.print(str(row))


def _render_dict(data) -> None:
    table = Table("field", "value")
    for key, value in data.items():
        table.add_row(str(key), str(value))
    console.print(table)
