"""Interactive selection UI for search results."""

import logging

from rich.console import Console
from rich.prompt import IntPrompt
from rich.table import Table

from safaribooks.core.models import SearchResult

logger = logging.getLogger(__name__)


def select_book(
    console: Console,
    results: list[SearchResult],
    query: str,
) -> SearchResult | None:
    """Present search results and prompt the user to select one.

    Parameters
    ----------
    console:
        Rich console for output.
    results:
        List of search results to display.
    query:
        The original search query (shown in the header).

    Returns:
    -------
    SearchResult | None
        The selected result, or ``None`` if the user cancels.

    """
    if not results:
        return None

    console.print(f'\n[bold]Found {len(results)} book(s) matching[/] "[cyan]{query}[/]":\n')

    table = Table(show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Title", min_width=30)
    table.add_column("Author(s)", min_width=15)
    table.add_column("ID", width=16)
    table.add_column("Published", width=12)

    for idx, result in enumerate(results, start=1):
        authors = ", ".join(result.authors) if result.authors else "[dim]Unknown[/dim]"
        table.add_row(
            str(idx),
            result.title,
            authors,
            result.book_id,
            result.issued or "[dim]n/a[/dim]",
        )

    console.print(table)
    console.print()

    if not console.is_terminal:
        console.print("[yellow]Non-interactive mode — auto-selecting first result.[/]")
        selected = results[0]
        console.print(f"[green]Selected:[/] {selected.title} ({selected.book_id})")
        return selected

    choice = IntPrompt.ask(
        f"[bold]Select a book[/] [dim][1-{len(results)}, 0 to cancel][/dim]",
        console=console,
        default=1,
    )

    if choice == 0:
        console.print("[yellow]Selection cancelled.[/]")
        return None
    if 1 <= choice <= len(results):
        selected = results[choice - 1]
        console.print(f"[green]Selected:[/] {selected.title} ({selected.book_id})")
        return selected

    console.print("[red]Invalid selection.[/]")
    return None
