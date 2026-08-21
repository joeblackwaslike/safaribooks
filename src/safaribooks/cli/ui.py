"""Interactive selection UI for search results."""

import logging

from rich.console import Console
from rich.prompt import IntPrompt
from rich.table import Table

from safaribooks.core.models import SearchResult

logger = logging.getLogger(__name__)

_TITLE_MIN_WIDTH = 30
_AUTHORS_MIN_WIDTH = 15
_ID_WIDTH = 16
_PUBLISHED_WIDTH = 12

_UNKNOWN_AUTHORS = "[dim]Unknown[/dim]"
_MISSING_DATE = "[dim]n/a[/dim]"


def _build_results_table(books: list[SearchResult]) -> Table:
    """Build the Rich table listing the search results."""
    table = Table(show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Title", min_width=_TITLE_MIN_WIDTH)
    table.add_column("Author(s)", min_width=_AUTHORS_MIN_WIDTH)
    table.add_column("ID", width=_ID_WIDTH)
    table.add_column("Published", width=_PUBLISHED_WIDTH)

    for idx, entry in enumerate(books, start=1):
        authors = ", ".join(entry.authors) if entry.authors else _UNKNOWN_AUTHORS
        table.add_row(
            str(idx),
            entry.title,
            authors,
            entry.book_id,
            entry.issued or _MISSING_DATE,
        )

    return table


def _announce_selection(console: Console, selected: SearchResult) -> SearchResult:
    """Report the chosen result and return it unchanged."""
    console.print(f"[green]Selected:[/] {selected.title} ({selected.book_id})")
    return selected


def _prompt_for_choice(console: Console, books: list[SearchResult]) -> SearchResult | None:
    """Prompt the user interactively and resolve their choice."""
    choice = IntPrompt.ask(
        f"[bold]Select a book[/] [dim][1-{len(books)}, 0 to cancel][/dim]",
        console=console,
        default=1,
    )

    if choice == 0:
        console.print("[yellow]Selection cancelled.[/]")
        return None
    if 1 <= choice <= len(books):
        return _announce_selection(console, books[choice - 1])

    console.print("[red]Invalid selection.[/]")
    return None


def select_book(
    console: Console,
    search_results: list[SearchResult],
    query: str,
) -> SearchResult | None:
    """Present search results and prompt the user to select one.

    Parameters
    ----------
    console:
        Rich console for output.
    search_results:
        List of search results to display.
    query:
        The original search query (shown in the header).

    Returns:
    -------
    SearchResult | None
        The selected result, or ``None`` if the user cancels.

    """
    if not search_results:
        return None

    console.print(
        f'\n[bold]Found {len(search_results)} book(s) matching[/] "[cyan]{query}[/]":\n',
    )
    console.print(_build_results_table(search_results))
    console.print()

    if not console.is_terminal:
        console.print("[yellow]Non-interactive mode — auto-selecting first result.[/]")
        return _announce_selection(console, search_results[0])

    return _prompt_for_choice(console, search_results)
