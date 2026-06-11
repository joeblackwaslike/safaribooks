"""Tests for safaribooks.cli.ui — interactive book selection."""


import io
from unittest.mock import patch

from rich.console import Console

from safaribooks.cli.ui import select_book
from safaribooks.core.models import SearchResult


def _make_results(count: int = 3) -> list[SearchResult]:
    return [
        SearchResult(
            title=f"Book {i}",
            isbn=f"978000000000{i}",
            authors=[f"Author {i}"],
            issued=f"2024-0{i}-01",
        )
        for i in range(1, count + 1)
    ]


class TestSelectBook:
    def test_select_first_result(self):
        results = _make_results()
        console = Console(file=io.StringIO(), force_terminal=True)

        with patch("safaribooks.cli.ui.IntPrompt.ask", return_value=1):
            selected = select_book(console, results, "test query")

        assert selected is not None
        assert selected.title == "Book 1"
        assert selected.book_id == "9780000000001"

    def test_select_second_result(self):
        results = _make_results()
        console = Console(file=io.StringIO(), force_terminal=True)

        with patch("safaribooks.cli.ui.IntPrompt.ask", return_value=2):
            selected = select_book(console, results, "test query")

        assert selected is not None
        assert selected.title == "Book 2"

    def test_cancel_returns_none(self):
        results = _make_results()
        console = Console(file=io.StringIO(), force_terminal=True)

        with patch("safaribooks.cli.ui.IntPrompt.ask", return_value=0):
            selected = select_book(console, results, "test query")

        assert selected is None

    def test_invalid_selection_returns_none(self):
        results = _make_results()
        console = Console(file=io.StringIO(), force_terminal=True)

        with patch("safaribooks.cli.ui.IntPrompt.ask", return_value=99):
            selected = select_book(console, results, "test query")

        assert selected is None

    def test_empty_results_returns_none(self):
        console = Console(file=io.StringIO())
        selected = select_book(console, [], "test query")
        assert selected is None

    def test_table_shows_titles(self):
        results = _make_results()
        output = io.StringIO()
        console = Console(file=output, force_terminal=True)

        with patch("safaribooks.cli.ui.IntPrompt.ask", return_value=1):
            select_book(console, results, "test query")

        text = output.getvalue()
        assert "Book 1" in text
        assert "Book 2" in text
        assert "Book 3" in text
        assert "test query" in text

    def test_non_interactive_auto_selects_first(self):
        results = _make_results()
        output = io.StringIO()
        console = Console(file=output, force_terminal=False)

        selected = select_book(console, results, "test query")

        assert selected is not None
        assert selected.title == "Book 1"
        text = output.getvalue()
        assert "auto-selecting" in text.lower() or "Non-interactive" in text
