"""Command-line interface for safaribooks (built in Phase 3)."""


from importlib.metadata import version as _pkg_version
from typing import Annotated

import typer
from rich.console import Console

from safaribooks.cli import auth
from safaribooks.cli.fetch import fetch_cmd

app = typer.Typer(
    name="safari",
    help="[bold cyan]safari[/] — download O'Reilly books as EPUB.",
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()

app.add_typer(auth.app, name="auth")
app.command("fetch")(fetch_cmd)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    *,
    version: Annotated[
        bool,
        typer.Option("--version", "-v", help="Show version and exit.", is_eager=True),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Enable debug logging.", envvar="SAFARI_DEBUG"),
    ] = False,
) -> None:
    """Safari Books downloader CLI."""
    if version:
        console.print(f"[bold cyan]safari[/] [green]{_pkg_version('safaribooks')}[/]")
        raise typer.Exit

    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
