"""Fetch command — download books from O'Reilly Learning Platform."""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn

from safaribooks.cli.ui import select_book
from safaribooks.core.config import AppConfig
from safaribooks.core.downloader import BookDownloader, extract_book_id, fetch_playlist_book_ids
from safaribooks.core.exceptions import SafariBooksError
from safaribooks.core.log import configure_async_logging

if TYPE_CHECKING:
    from safaribooks.core.api import ApiClient
    from safaribooks.core.models import SearchResult

logger = logging.getLogger(__name__)

console = Console()

_EXIT_INTERRUPTED = 130
_FALLBACK_TOTAL = 1


@dataclass
class _CollectedInputs:
    """Partitioned user inputs: resolved IDs and unresolved title queries."""

    book_ids: list[str] = field(default_factory=list)
    title_queries: list[str] = field(default_factory=list)

    @classmethod
    def collect(cls, book_ids: list[str] | None, id_file: Path | None) -> "_CollectedInputs":
        """Gather and partition inputs into book IDs and title queries."""
        collected = cls()
        raw_ids: list[str] = list(book_ids or [])
        if id_file:
            raw_ids.extend(collected._read_id_lines(id_file))

        for raw in raw_ids:
            book_id = extract_book_id(raw)
            if book_id is None:
                collected.title_queries.append(raw)
            else:
                collected.book_ids.append(book_id)
        return collected

    def _read_id_lines(self, ids_file: Path) -> list[str]:
        """Read non-empty, stripped lines from an IDs file."""
        if not ids_file.is_file():
            console.print(f"[red]Error:[/] File not found: {ids_file}")
            raise typer.Exit(code=1)
        text = ids_file.read_text(encoding="utf-8")
        return [line.strip() for line in text.splitlines() if line.strip()]


class _ProgressCallback:
    """Stateful progress callback that updates a rich progress bar.

    The call signature matches ``BookDownloader.progress_callback``:
    ``(stage: str, current: int, total: int) -> None``.
    """

    def __init__(self, progress: Progress) -> None:
        self._progress = progress
        self._stage_tasks: dict[str, TaskID] = {}

    def __call__(self, stage: str, current: int, total: int) -> None:
        if stage not in self._stage_tasks:
            self._stage_tasks[stage] = self._progress.add_task(
                f"  [dim]{stage}[/]",
                total=total or _FALLBACK_TOTAL,
            )
        tid = self._stage_tasks[stage]
        self._progress.update(tid, completed=current, total=total or _FALLBACK_TOTAL)


def fetch_cmd(  # noqa: WPS211 -- one param per CLI flag; Typer has no native
    # way to expand a dataclass/model into flags (checked current Typer docs),
    # so grouping these into a config object would break flag generation.
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
    id_file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="File with book IDs, one per line."),
    ] = None,
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
    markdown: Annotated[
        bool,
        typer.Option("--markdown", help="Also write an LLM-oriented Markdown file."),
    ] = False,
    markdown_only: Annotated[
        bool,
        typer.Option("--markdown-only", help="Write only the Markdown file, skip the EPUB."),
    ] = False,
) -> None:
    """Download books from O'Reilly Learning Platform."""
    debug = (ctx.obj or {}).get("debug", False)

    # Validate at least one source of book IDs or title queries
    if not book_ids and not playlist and not id_file:
        console.print("[red]Error:[/] Provide book IDs, titles, --playlist, or --file.")
        raise typer.Exit(code=1)

    config_kwargs: dict[str, object] = {
        "image_max_size": image_max_size,
        "image_quality": image_quality,
        "ssl_skip": ssl_skip,
        "preserve_log": preserve_log,
        "debug": debug,
        "rate_limit": rate_limit,
        "rate_burst": rate_burst,
        "markdown": markdown or markdown_only,
        "markdown_only": markdown_only,
    }
    if output_dir:
        config_kwargs["output_dir"] = output_dir
    if library_dir:
        config_kwargs["library_dir"] = library_dir
    config = AppConfig(**config_kwargs)  # type: ignore[arg-type]

    # Collect and partition inputs
    inputs = _CollectedInputs.collect(book_ids, id_file)

    # Run async pipeline
    asyncio.run(_fetch_async(config, inputs, playlist, console))


@dataclass
class _DownloadOutcome:
    """Accumulated successes and failures across a download run."""

    succeeded: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def print_summary(self, con: Console) -> None:
        """Print the post-download summary of successes and failures."""
        con.print()
        con.rule("[bold]Summary[/]")
        if self.succeeded:
            con.print(f"[green]Downloaded:[/] {len(self.succeeded)} book(s)")
        if self.failed:
            con.print(f"[red]Failed:[/] {len(self.failed)} book(s)")
            for bid, reason in self.failed:
                con.print(f"  [dim]{bid}:[/] {reason}")


class _Resolver:
    """Resolve title queries and playlists into concrete book IDs."""

    def __init__(self, config: AppConfig, con: Console) -> None:
        self._config = config
        self._con = con

    async def resolve(self, inputs: _CollectedInputs, playlist: str | None) -> list[str]:
        """Resolve title queries and playlists into a full list of book IDs."""
        all_ids = list(inputs.book_ids)
        if not (inputs.title_queries or playlist):
            return all_ids

        # Deferred: tests patch `safaribooks.core.api.ApiClient` directly, which
        # only takes effect if the name is looked up fresh at call time.
        from safaribooks.core.api import ApiClient  # noqa: PLC0415

        async with ApiClient(self._config) as client:
            await self._resolve_titles(client, inputs.title_queries, all_ids)
            if playlist:
                await self._resolve_playlist(client, playlist, all_ids)
        return all_ids

    async def _resolve_titles(
        self,
        client: "ApiClient",
        queries: list[str],
        all_ids: list[str],
    ) -> None:
        """Resolve each title query and append any matched IDs in order."""
        index = 0
        while index < len(queries):
            book_id = await self._resolve_one_query(client, queries[index])
            index += 1
            if book_id:
                all_ids.append(book_id)

    async def _resolve_one_query(self, client: "ApiClient", query: str) -> str | None:
        """Resolve a single title query into a book ID, or ``None``."""
        # Deferred: tests patch `safaribooks.core.search.search_books` directly,
        # which only takes effect if the name is looked up fresh at call time.
        from safaribooks.core.search import search_books  # noqa: PLC0415

        self._con.print(f'[cyan]Searching for[/] "[bold]{query}[/]"...')
        try:
            response = await search_books(client, query)
        except SafariBooksError as exc:
            self._con.print(f"[red]Search error:[/] {exc}")
            return None

        if not response.results:
            self._con.print(f'[yellow]Warning:[/] No books found matching "{query}".')
            return None
        return self._pick_book_id(response.results, query)

    def _pick_book_id(self, found: list["SearchResult"], query: str) -> str | None:
        """Pick a book ID from results, auto-selecting a sole match or prompting."""
        if len(found) > 1:
            selected = select_book(self._con, found, query)
        else:
            selected = found[0]
            self._con.print(f"[green]Found:[/] {selected.title} ({selected.book_id})")

        if selected and selected.book_id:
            return selected.book_id
        return None

    async def _resolve_playlist(
        self,
        client: "ApiClient",
        playlist: str,
        all_ids: list[str],
    ) -> None:
        """Fetch a playlist's book IDs and append them in order."""
        self._con.print(f"[cyan]Fetching playlist {playlist}...[/]")
        try:
            playlist_ids = await fetch_playlist_book_ids(client, playlist)
        except SafariBooksError as exc:
            self._con.print(f"[red]Error fetching playlist:[/] {exc}")
            raise typer.Exit(code=1) from None

        for raw in playlist_ids:
            book_id = extract_book_id(raw)
            if book_id is not None:
                all_ids.append(book_id)
        self._con.print(f"  Found [bold]{len(playlist_ids)}[/] books in playlist.")


class _Pipeline:
    """Coordinate ID resolution and sequential book downloads for one run.

    Used as an async context manager so the async log handler is started on
    entry and always stopped on exit.
    """

    def __init__(self, config: AppConfig, con: Console) -> None:
        self._config = config
        self._con = con
        self._log_handler: Any = None

    async def __aenter__(self) -> "_Pipeline":

        self._log_handler = configure_async_logging(
            level=logging.DEBUG if self._config.debug else logging.INFO,
        )
        await self._log_handler.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        if self._log_handler is not None:
            await self._log_handler.stop()

    async def run(self, inputs: _CollectedInputs, playlist: str | None) -> None:
        """Resolve all book IDs, download them, then print the summary."""
        all_ids = await _Resolver(self._config, self._con).resolve(inputs, playlist)
        if not all_ids:
            self._con.print("[red]Error:[/] No valid book IDs found.")
            raise typer.Exit(code=1)

        self._con.print(f"[bold cyan]Downloading {len(all_ids)} book(s)...[/]\n")
        outcome = await self._download_all(all_ids)
        outcome.print_summary(self._con)
        if outcome.failed and not outcome.succeeded:
            raise typer.Exit(code=1)

    async def _download_all(self, all_ids: list[str]) -> _DownloadOutcome:
        """Download every book sequentially, collecting successes and failures."""
        outcome = _DownloadOutcome()
        index = 0
        while index < len(all_ids):
            book_id = all_ids[index]
            index += 1
            self._con.rule(f"[bold]Book {index}/{len(all_ids)}: {book_id}[/]")
            epub_path = await self._download_one(book_id, outcome)
            if epub_path is not None:
                self._con.print(f"[green]Saved:[/] {epub_path}\n")
                outcome.succeeded.append(book_id)
        return outcome

    async def _download_one(self, book_id: str, outcome: _DownloadOutcome) -> Path | None:
        """Download a single book, recording failures and returning its path."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self._con,
        ) as progress:
            progress.add_task(f"[bold]{book_id}[/]", total=None)
            callback = _ProgressCallback(progress)
            downloader = BookDownloader(self._config, book_id, progress_callback=callback)
            return await self._run_downloader(downloader, book_id, progress, outcome)

    async def _run_downloader(
        self,
        downloader: BookDownloader,
        book_id: str,
        progress: Progress,
        outcome: _DownloadOutcome,
    ) -> Path | None:
        """Run one downloader, translating its errors into outcome entries."""
        try:
            return await downloader.run()
        except SafariBooksError as exc:
            progress.stop()
            self._con.print(f"\n[red]Failed:[/] {exc}")
            outcome.failed.append((book_id, str(exc)))
            return None
        except KeyboardInterrupt:
            progress.stop()
            self._con.print("\n[yellow]Interrupted by user.[/]")
            raise typer.Exit(code=_EXIT_INTERRUPTED) from None


async def _fetch_async(
    config: AppConfig,
    inputs: _CollectedInputs,
    playlist: str | None,
    con: Console,
) -> None:
    """Async pipeline: resolve title queries, playlists, and download books."""
    async with _Pipeline(config, con) as pipeline:
        await pipeline.run(inputs, playlist)
