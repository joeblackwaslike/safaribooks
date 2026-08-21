"""Auth command group — manage O'Reilly session cookies."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from safaribooks.core import cookies as cookie_mod
from safaribooks.core.config import AppConfig
from safaribooks.core.exceptions import CookieError

app = typer.Typer(
    help="[bold cyan]auth[/] — manage O'Reilly session cookies.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

console = Console()

_ERROR_PREFIX = "[red]Error:[/]"
_PREVIEW_LIMIT = 40


def _default_cookie_path() -> Path:
    """Return the default cookie file path from AppConfig."""
    return AppConfig().cookies_file


def _preview(cookie_value: str) -> str:
    """Truncate a cookie value for display, appending an ellipsis when long."""
    if len(cookie_value) > _PREVIEW_LIMIT:
        head = cookie_value[:_PREVIEW_LIMIT]
        return f"{head}..."
    return cookie_value


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
        cookie_set = cookie_mod.from_paste()
    except CookieError as exc:
        console.print(f"{_ERROR_PREFIX} {exc}")
        raise typer.Exit(code=1) from None

    cookie_mod.save(cookie_set, dest)
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
        cookie_set = cookie_mod.from_browser(browser)
    except CookieError as exc:
        console.print(f"{_ERROR_PREFIX} {exc}")
        raise typer.Exit(code=1) from None

    cookie_mod.save(cookie_set, dest)
    console.print(f"[green]Cookies saved to {dest}[/] ({len(cookie_set.cookies)} cookies)")


@app.command(name="import")
def import_cookies(
    *,
    import_file: Annotated[
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
    if not import_file and not header:
        console.print(f"{_ERROR_PREFIX} Provide --file or --header.")
        raise typer.Exit(code=1)

    dest = output or _default_cookie_path()
    try:
        if import_file:
            cookie_set = cookie_mod.from_file(import_file)
        else:
            if header is None:  # guarded above; defensive fallback
                console.print(f"{_ERROR_PREFIX} Provide --file or --header.")
                raise typer.Exit(code=1)
            cookie_set = cookie_mod.from_header(header)
    except CookieError as exc:
        console.print(f"{_ERROR_PREFIX} {exc}")
        raise typer.Exit(code=1) from None

    cookie_mod.save(cookie_set, dest)
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
        console.print(f"{_ERROR_PREFIX} Cookie file not found: {path}")
        raise typer.Exit(code=1)

    try:
        cookie_set = cookie_mod.from_file(path)
    except CookieError as exc:
        console.print(f"{_ERROR_PREFIX} {exc}")
        raise typer.Exit(code=1) from None

    console.print(f"[green]Valid![/] {len(cookie_set.cookies)} cookies in {path}")
    for key in sorted(cookie_set.cookies):
        preview = _preview(cookie_set.cookies[key])
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
        cookie_set = cookie_mod.from_file(path)
    except CookieError as exc:
        console.print(f"[red]Status:[/] Invalid — {exc}")
        return

    stat_result = path.stat()
    size_kb = stat_result.st_size / 1024
    console.print(f"[green]Status:[/] Valid ({len(cookie_set.cookies)} cookies, {size_kb:.1f} KB)")
    for key in sorted(cookie_set.cookies):
        console.print(f"  [dim]{key}[/]")
