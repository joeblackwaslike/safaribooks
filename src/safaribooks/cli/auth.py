"""Auth command group — manage O'Reilly session cookies."""


from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from safaribooks.core.config import AppConfig
from safaribooks.core.cookies import (
    from_browser,
    from_file,
    from_header,
    from_paste,
    save,
)
from safaribooks.core.exceptions import CookieError

app = typer.Typer(
    help="[bold cyan]auth[/] — manage O'Reilly session cookies.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

console = Console()


def _default_cookie_path() -> Path:
    """Return the default cookie file path from AppConfig."""
    return AppConfig().cookies_file


@app.command()
def setup(
    *,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Cookie file output path."),
    ] = None,
) -> None:
    """Interactive cookie paste — paste cookies from your browser."""
    dest = output or _default_cookie_path()
    try:
        cookie_set = from_paste()
    except CookieError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(code=1) from None

    save(cookie_set, dest)
    console.print(f"[green]Cookies saved to {dest}[/] ({len(cookie_set.cookies)} cookies)")


@app.command()
def extract(
    *,
    browser: Annotated[
        str,
        typer.Option("--browser", "-b", help="Browser to extract from."),
    ] = "chrome",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Cookie file output path."),
    ] = None,
) -> None:
    """Extract cookies from an installed browser automatically."""
    dest = output or _default_cookie_path()
    try:
        cookie_set = from_browser(browser)
    except CookieError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(code=1) from None

    save(cookie_set, dest)
    console.print(f"[green]Cookies saved to {dest}[/] ({len(cookie_set.cookies)} cookies)")


@app.command(name="import")
def import_cookies(
    *,
    file: Annotated[
        Path | None,
        typer.Option(
            "--file", "-f", help="Path to a cookie file (JSON, header, or extension export)."
        ),
    ] = None,
    header: Annotated[
        str | None,
        typer.Option("--header", "-H", help="Raw 'Cookie: k=v; k2=v2' header string."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Cookie file output path."),
    ] = None,
) -> None:
    """Import cookies from a file or header string."""
    if not file and not header:
        console.print("[red]Error:[/] Provide --file or --header.")
        raise typer.Exit(code=1)

    dest = output or _default_cookie_path()
    try:
        if file:
            cookie_set = from_file(file)
        else:
            assert header is not None  # noqa: S101 — guarded above
            cookie_set = from_header(header)
    except CookieError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(code=1) from None

    save(cookie_set, dest)
    console.print(f"[green]Cookies saved to {dest}[/] ({len(cookie_set.cookies)} cookies)")


@app.command(name="validate")
def validate_cmd(
    *,
    cookie_file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Cookie file to validate."),
    ] = None,
) -> None:
    """Validate existing cookies."""
    path = cookie_file or _default_cookie_path()
    if not path.is_file():
        console.print(f"[red]Error:[/] Cookie file not found: {path}")
        raise typer.Exit(code=1)

    try:
        cookie_set = from_file(path)
    except CookieError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(code=1) from None

    console.print(f"[green]Valid![/] {len(cookie_set.cookies)} cookies in {path}")
    for key in sorted(cookie_set.cookies):
        val = cookie_set.cookies[key]
        preview = val[:40] + "..." if len(val) > 40 else val
        console.print(f"  [dim]{key}[/] = {preview}")


@app.command()
def status() -> None:
    """Show cookie file location and info."""
    path = _default_cookie_path()
    console.print(f"[bold]Cookie file:[/] {path}")

    if not path.is_file():
        console.print("[yellow]Status:[/] No cookie file found. Run [bold]safari auth setup[/].")
        return

    try:
        cookie_set = from_file(path)
    except CookieError as exc:
        console.print(f"[red]Status:[/] Invalid — {exc}")
        return

    stat_result = path.stat()
    size_kb = stat_result.st_size / 1024
    console.print(f"[green]Status:[/] Valid ({len(cookie_set.cookies)} cookies, {size_kb:.1f} KB)")
    for key in sorted(cookie_set.cookies):
        console.print(f"  [dim]{key}[/]")
