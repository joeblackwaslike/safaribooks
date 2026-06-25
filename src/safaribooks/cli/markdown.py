"""Markdown command — convert an existing EPUB into an LLM-oriented Markdown file."""

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from safaribooks.core.config import AppConfig
from safaribooks.core.exceptions import SafariBooksError
from safaribooks.core.markdown import convert_epub

logger = logging.getLogger(__name__)
console = Console()

_MD_SUFFIX = ".md"


def markdown_cmd(
    epub: Annotated[
        Path,
        typer.Argument(help="Path to an existing .epub file to convert."),
    ],
    *,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory (default: beside the EPUB)."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing Markdown file."),
    ] = False,
) -> None:
    """Convert an existing EPUB to an LLM-oriented Markdown file.

    Extensions are read from ``~/.config/safaribooks/config.toml``
    (``markdown_extensions = [...]``), in list order.
    """
    config = AppConfig()
    destination = (output_dir or epub.parent) / (epub.stem + _MD_SUFFIX)
    try:
        written_path = convert_epub(
            epub,
            destination,
            extensions=config.markdown_extensions,
            force=force,
        )
    except FileExistsError:
        console.print(f"[red]Error:[/] {destination} exists. Use [bold]--force[/] to overwrite.")
        raise typer.Exit(code=1) from None
    except SafariBooksError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Saved:[/] {written_path}")
