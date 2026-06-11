"""Fetch command — download books from O'Reilly Learning Platform."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn

from safaribooks.core.config import AppConfig
from safaribooks.core.downloader import BookDownloader, extract_book_id, fetch_playlist_book_ids
from safaribooks.core.exceptions import SafariBooksError

logger = logging.getLogger(__name__)

console = Console()


@dataclass
class _CollectedInputs:
    """Partitioned user inputs: resolved IDs and unresolved title queries."""

    book_ids: list[str] = field(default_factory=list)
    title_queries: list[str] = field(default_factory=list)


def _collect_book_ids(
    book_ids: list[str] | None,
    file: Path | None,
) -> _CollectedInputs:
    """Gather and partition inputs into book IDs and title queries."""
    raw_ids: list[str] = []

    if book_ids:
        raw_ids.extend(book_ids)

    if file:
        if not file.is_file():
            console.print(f"[red]Error:[/] File not found: {file}")
            raise typer.Exit(code=1)
        raw_ids.extend(
            line.strip() for line in file.read_text(encoding="utf-8").splitlines() if line.strip()
        )

    result = _CollectedInputs()
    for raw in raw_ids:
        book_id = extract_book_id(raw)
        if book_id is not None:
            result.book_ids.append(book_id)
        else:
            result.title_queries.append(raw)

    return result


def _make_progress_callback(
    progress: Progress,
    _task_id: int,
) -> Callable[[str, int, int], None]:
    """Create a progress callback that updates a rich progress bar.

    The callback signature matches ``BookDownloader.progress_callback``:
    ``(stage: str, current: int, total: int) -> None``.
    """
    stage_tasks: dict[str, TaskID] = {}

    def _callback(stage: str, current: int, total: int) -> None:
        if stage not in stage_tasks:
            stage_tasks[stage] = progress.add_task(f"  [dim]{stage}[/]", total=total or 1)
        tid = stage_tasks[stage]
        progress.update(tid, completed=current, total=total or 1)

    return _callback


def fetch_cmd(
    ctx: typer.Context,
    book_ids: Annotated[
        list[str] | None,
        typer.Argument(help="Book IDs, O'Reilly URLs, or title searches to download."),
    ] = None,
    *,
    playlist: Annotated[
        str | None,
        typer.Option("--playlist", "-p", help="Download all books from a playlist UUID."),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="File with book IDs, one per line."),
    ] = None,
    kindle: Annotated[
        bool,
        typer.Option("--kindle", help="Add Kindle-compatible CSS."),
    ] = False,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory."),
    ] = None,
    library_dir: Annotated[
        Path | None,
        typer.Option("--library-dir", help="Central library directory for collected EPUBs."),
    ] = None,
    image_max_size: Annotated[
        int,
        typer.Option("--image-max-size", help="Max image dimension (0=no resize)."),
    ] = 0,
    image_quality: Annotated[
        int,
        typer.Option("--image-quality", help="JPEG quality 1-95 (0=keep original)."),
    ] = 0,
    ssl_skip: Annotated[
        bool,
        typer.Option("--ssl-skip", help="Skip SSL certificate verification."),
    ] = False,
    preserve_log: Annotated[
        bool,
        typer.Option("--preserve-log", help="Keep log file even without errors."),
    ] = False,
    rate_limit: Annotated[
        float,
        typer.Option("--rate-limit", "-r", help="Max requests per second (0=unlimited)."),
    ] = 1.0,
    rate_burst: Annotated[
        int,
        typer.Option("--rate-burst", help="Rate limiter burst capacity."),
    ] = 2,
) -> None:
    """Download books from O'Reilly Learning Platform."""
    debug = (ctx.obj or {}).get("debug", False)

    # Validate at least one source of book IDs or title queries
    if not book_ids and not playlist and not file:
        console.print("[red]Error:[/] Provide book IDs, titles, --playlist, or --file.")
        raise typer.Exit(code=1)

    # Build AppConfig from CLI options
    config_kwargs: dict[str, object] = {
        "kindle": kindle,
        "image_max_size": image_max_size,
        "image_quality": image_quality,
        "ssl_skip": ssl_skip,
        "preserve_log": preserve_log,
        "debug": debug,
        "rate_limit": rate_limit,
        "rate_burst": rate_burst,
    }
    if output_dir:
        config_kwargs["output_dir"] = output_dir
    if library_dir:
        config_kwargs["library_dir"] = library_dir
    config = AppConfig(**config_kwargs)  # type: ignore[arg-type]

    # Collect and partition inputs
    inputs = _collect_book_ids(book_ids, file)

    # Run async pipeline
    asyncio.run(_fetch_async(config, inputs, playlist, console))


async def _fetch_async(
    config: AppConfig,
    inputs: _CollectedInputs,
    playlist: str | None,
    con: Console,
) -> None:
    """Async pipeline: resolve title queries, playlists, and download books."""
    from safaribooks.cli.ui import select_book  # noqa: PLC0415
    from safaribooks.core.log import configure_async_logging  # noqa: PLC0415
    from safaribooks.core.models import SearchResult  # noqa: PLC0415
    from safaribooks.core.search import search_books  # noqa: PLC0415

    handler = configure_async_logging(
        level=logging.DEBUG if config.debug else logging.INFO,
    )
    await handler.start()

    try:
        all_ids = list(inputs.book_ids)

        # Resolve title queries and playlists (both need async ApiClient)
        if inputs.title_queries or playlist:
            from safaribooks.core.api import ApiClient  # noqa: PLC0415

            async with ApiClient(config) as client:
                # Resolve title queries via search API
                for query in inputs.title_queries:
                    con.print(f'[cyan]Searching for[/] "[bold]{query}[/]"...')
                    try:
                        response = await search_books(client, query)
                    except SafariBooksError as exc:
                        con.print(f"[red]Search error:[/] {exc}")
                        continue

                    if not response.results:
                        con.print(f'[yellow]Warning:[/] No books found matching "{query}".')
                        continue

                    selected: SearchResult | None
                    if len(response.results) == 1:
                        selected = response.results[0]
                        con.print(f"[green]Found:[/] {selected.title} ({selected.book_id})")
                    else:
                        selected = select_book(con, response.results, query)

                    if selected and selected.book_id:
                        all_ids.append(selected.book_id)

                # Handle playlist
                if playlist:
                    con.print(f"[cyan]Fetching playlist {playlist}...[/]")
                    try:
                        playlist_ids = await fetch_playlist_book_ids(client, playlist)
                    except SafariBooksError as exc:
                        con.print(f"[red]Error fetching playlist:[/] {exc}")
                        raise typer.Exit(code=1) from None
                    for raw in playlist_ids:
                        book_id = extract_book_id(raw)
                        if book_id is not None:
                            all_ids.append(book_id)
                    con.print(f"  Found [bold]{len(playlist_ids)}[/] books in playlist.")

        if not all_ids:
            con.print("[red]Error:[/] No valid book IDs found.")
            raise typer.Exit(code=1)

        con.print(f"[bold cyan]Downloading {len(all_ids)} book(s)...[/]\n")

        succeeded: list[str] = []
        failed: list[tuple[str, str]] = []

        for idx, book_id in enumerate(all_ids, start=1):
            con.rule(f"[bold]Book {idx}/{len(all_ids)}: {book_id}[/]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=con,
            ) as progress:
                main_task = progress.add_task(f"[bold]{book_id}[/]", total=None)
                callback = _make_progress_callback(progress, main_task)

                downloader = BookDownloader(config, book_id, progress_callback=callback)
                try:
                    epub_path = await downloader.run()
                except SafariBooksError as exc:
                    progress.stop()
                    con.print(f"\n[red]Failed:[/] {exc}")
                    failed.append((book_id, str(exc)))
                    continue
                except KeyboardInterrupt:
                    progress.stop()
                    con.print("\n[yellow]Interrupted by user.[/]")
                    raise typer.Exit(code=130) from None

            con.print(f"[green]Saved:[/] {epub_path}\n")
            succeeded.append(book_id)

        # Summary
        con.print()
        con.rule("[bold]Summary[/]")
        if succeeded:
            con.print(f"[green]Downloaded:[/] {len(succeeded)} book(s)")
        if failed:
            con.print(f"[red]Failed:[/] {len(failed)} book(s)")
            for bid, reason in failed:
                con.print(f"  [dim]{bid}:[/] {reason}")

        if failed and not succeeded:
            raise typer.Exit(code=1)
    finally:
        await handler.stop()
