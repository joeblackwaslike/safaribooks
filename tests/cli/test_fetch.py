"""Tests for the ``safari fetch`` CLI command."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import click
from typer.testing import CliRunner

from safaribooks.cli import app
from safaribooks.core.exceptions import ApiError, SafariBooksError, SearchError
from safaribooks.core.models import SearchResponse, SearchResult

runner = CliRunner()

_EXPECTED_IMAGE_MAX_SIZE = 800
_EXPECTED_IMAGE_QUALITY = 85
_EPUB_FILENAME = "book.epub"


def _stub_downloader(
    downloader_cls: MagicMock,
    output_dir: Path,
    filename: str = _EPUB_FILENAME,
) -> MagicMock:
    """Configure a BookDownloader mock class to return a runnable instance."""
    instance = MagicMock()
    instance.run = AsyncMock(return_value=output_dir / filename)
    downloader_cls.return_value = instance
    return instance


def _invoke_fetch(*book_args: str, output: Path):
    """Invoke ``safari fetch`` with the shared ``--output`` destination."""
    return runner.invoke(app, ["fetch", *book_args, "--output", str(output)])


def _invoke_fetch_ok(*book_args: str, output: Path):
    """Invoke ``safari fetch`` and assert it exits successfully."""
    invoke_result = _invoke_fetch(*book_args, output=output)
    assert invoke_result.exit_code == 0
    return invoke_result


def _run_download(downloader_cls: MagicMock, *book_args: str, output: Path):
    """Stub the downloader then run a successful fetch in one step."""
    _stub_downloader(downloader_cls, output)
    return _invoke_fetch_ok(*book_args, output=output)


class _FirstFailsFactory:
    """BookDownloader side_effect: first instance fails, the rest succeed."""

    def __init__(self, success_path: Path) -> None:
        self._success_path = success_path
        self._calls = 0

    def __call__(self, *args: object, **kwargs: object) -> MagicMock:
        self._calls += 1
        instance = MagicMock()
        if self._calls == 1:
            instance.run = AsyncMock(side_effect=SafariBooksError("Failed first"))
        else:
            instance.run = AsyncMock(return_value=self._success_path)
        return instance


def _stub_async_client(api_client_cls: MagicMock) -> MagicMock:
    """Make an ApiClient mock behave as an async context manager."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    api_client_cls.return_value = client
    return client


class TestFetchHelp:
    """Verify the fetch command surfaces all expected options."""

    def test_fetch_help_shows_book_ids_arg(self):
        output = self._help_output()
        assert "book-ids" in output.lower() or "BOOK_IDS" in output

    def test_fetch_help_shows_source_options(self):
        output = self._help_output()
        assert "--playlist" in output
        assert "--file" in output
        assert "--output" in output

    def test_fetch_help_shows_image_options(self):
        output = self._help_output()
        assert "--image-max-size" in output
        assert "--image-quality" in output

    def test_fetch_help_shows_misc_options(self):
        output = self._help_output()
        assert "--ssl-skip" in output
        assert "--preserve-log" in output

    def _help_output(self) -> str:
        # CI renders this with ANSI color codes (this shell's Rich Console
        # detects no color support, so locally it doesn't); Typer's option
        # highlighter then styles a flag's leading "-" separately from the
        # rest of the name, e.g. "--playlist" becomes two ANSI-coded spans
        # ("-" then "-playlist") with a reset sandwiched between them. That
        # breaks a plain substring check only when color is on. Strip ANSI
        # codes so the assertion is deterministic regardless of environment.
        invoke_result = runner.invoke(app, ["fetch", "--help"])
        assert invoke_result.exit_code == 0
        return click.unstyle(invoke_result.output)


class TestFetchNoArgs:
    """Verify fetch fails when no book IDs are provided."""

    def test_fetch_no_args_shows_error(self):
        invoke_result = runner.invoke(app, ["fetch"])
        assert invoke_result.exit_code == 1
        assert "Provide book IDs" in invoke_result.output or "Error" in invoke_result.output


class TestFetchWithBookId:
    """Verify fetch invokes BookDownloader with the correct book ID."""

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_single_book_id(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        instance = _stub_downloader(mock_downloader_cls, tmp_path, "test_book.epub")

        invoke_result = _invoke_fetch_ok("9781234567890", output=tmp_path)
        assert "Downloading 1 book(s)" in invoke_result.output

        mock_downloader_cls.assert_called_once()
        call_kwargs = mock_downloader_cls.call_args
        assert call_kwargs[0][1] == "9781234567890"  # positional: config, book_id

        instance.run.assert_called_once()

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_multiple_book_ids(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        invoke_result = _run_download(
            mock_downloader_cls,
            "9781111111111",
            "9782222222222",
            output=tmp_path,
        )
        assert "Downloading 2 book(s)" in invoke_result.output
        assert mock_downloader_cls.call_count == 2

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_url_input(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        """Verifies that a full O'Reilly URL is normalized to a bare book ID."""
        _run_download(
            mock_downloader_cls,
            "https://learning.oreilly.com/library/view/-/9781234567890/",
            output=tmp_path,
        )
        call_kwargs = mock_downloader_cls.call_args
        assert call_kwargs[0][1] == "9781234567890"


class TestFetchWithPlaylist:
    """Verify fetch with --playlist fetches playlist IDs then downloads."""

    @patch("safaribooks.cli.fetch.BookDownloader")
    @patch("safaribooks.cli.fetch.fetch_playlist_book_ids", new_callable=AsyncMock)
    @patch("safaribooks.core.api.ApiClient")
    def test_fetch_playlist(
        self,
        mock_api_client_cls: MagicMock,
        mock_fetch_playlist: AsyncMock,
        mock_downloader_cls: MagicMock,
        tmp_path: Path,
    ):
        mock_fetch_playlist.return_value = ["9781111111111", "9782222222222"]
        _stub_async_client(mock_api_client_cls)
        _stub_downloader(mock_downloader_cls, tmp_path)

        invoke_result = _invoke_fetch_ok(
            "--playlist",
            "some-playlist-uuid",
            output=tmp_path,
        )
        assert "Fetching playlist" in invoke_result.output
        assert "Found 2 books" in invoke_result.output
        assert "Downloading 2 book(s)" in invoke_result.output

        mock_fetch_playlist.assert_called_once()
        assert mock_downloader_cls.call_count == 2

    @patch("safaribooks.cli.fetch.fetch_playlist_book_ids", new_callable=AsyncMock)
    @patch("safaribooks.core.api.ApiClient")
    def test_fetch_playlist_api_error(
        self,
        mock_api_client_cls: MagicMock,
        mock_fetch_playlist: AsyncMock,
        tmp_path: Path,
    ):
        mock_fetch_playlist.side_effect = ApiError("Playlist not found")
        _stub_async_client(mock_api_client_cls)

        invoke_result = _invoke_fetch("--playlist", "bad-uuid", output=tmp_path)
        assert invoke_result.exit_code == 1
        assert "Error" in invoke_result.output


class TestFetchWithFile:
    """Verify fetch reads book IDs from a file."""

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_from_file(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        ids_file = tmp_path / "book_ids.txt"
        ids_file.write_text("9781111111111\n9782222222222\n\n9783333333333\n", encoding="utf-8")

        invoke_result = _run_download(
            mock_downloader_cls,
            "--file",
            str(ids_file),
            output=tmp_path,
        )
        assert "Downloading 3 book(s)" in invoke_result.output
        assert mock_downloader_cls.call_count == 3

    def test_fetch_from_missing_file(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.txt"
        invoke_result = _invoke_fetch("--file", str(missing), output=tmp_path)
        assert invoke_result.exit_code == 1
        assert "not found" in invoke_result.output.lower() or "Error" in invoke_result.output

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_from_file_with_urls(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        """IDs file with a mix of bare IDs and URLs."""
        ids_file = tmp_path / "ids.txt"
        ids_file.write_text(
            "9781111111111\nhttps://learning.oreilly.com/library/view/-/9782222222222/\n",
            encoding="utf-8",
        )

        invoke_result = _run_download(
            mock_downloader_cls,
            "--file",
            str(ids_file),
            output=tmp_path,
        )
        assert "Downloading 2 book(s)" in invoke_result.output


class TestFetchTitleQuery:
    """Verify non-ID inputs are resolved as title queries via the search API."""

    @patch("safaribooks.cli.fetch.BookDownloader")
    @patch("safaribooks.core.search.search_books", new_callable=AsyncMock)
    @patch("safaribooks.core.api.ApiClient")
    def test_title_single_result_auto_selects(
        self,
        mock_api_client_cls: MagicMock,
        mock_search: AsyncMock,
        mock_downloader_cls: MagicMock,
        tmp_path: Path,
    ):
        mock_search.return_value = SearchResponse(
            results=[SearchResult(title="Python Crash Course", isbn="9781718502703")],
            count=1,
        )
        _stub_async_client(mock_api_client_cls)
        _stub_downloader(mock_downloader_cls, tmp_path)

        invoke_result = _invoke_fetch_ok("Python Crash Course", output=tmp_path)
        assert "Searching for" in invoke_result.output
        assert "Downloading 1 book(s)" in invoke_result.output
        call_kwargs = mock_downloader_cls.call_args
        assert call_kwargs[0][1] == "9781718502703"

    @patch("safaribooks.core.search.search_books", new_callable=AsyncMock)
    @patch("safaribooks.core.api.ApiClient")
    def test_title_no_results_warns(
        self,
        mock_api_client_cls: MagicMock,
        mock_search: AsyncMock,
        tmp_path: Path,
    ):
        mock_search.return_value = SearchResponse(results=[], count=0)
        _stub_async_client(mock_api_client_cls)

        invoke_result = _invoke_fetch("nonexistent book xyz", output=tmp_path)
        assert invoke_result.exit_code == 1
        assert "No books found" in invoke_result.output

    @patch("safaribooks.cli.fetch.BookDownloader")
    @patch("safaribooks.core.search.search_books", new_callable=AsyncMock)
    @patch("safaribooks.core.api.ApiClient")
    def test_mixed_ids_and_titles(
        self,
        mock_api_client_cls: MagicMock,
        mock_search: AsyncMock,
        mock_downloader_cls: MagicMock,
        tmp_path: Path,
    ):
        """A numeric ID and a title query both resolve and download."""
        mock_search.return_value = SearchResponse(
            results=[SearchResult(title="Learning Go", isbn="9781492077213")],
            count=1,
        )
        _stub_async_client(mock_api_client_cls)
        _stub_downloader(mock_downloader_cls, tmp_path)

        invoke_result = _invoke_fetch_ok(
            "9781234567890",
            "Learning Go",
            output=tmp_path,
        )
        assert "Downloading 2 book(s)" in invoke_result.output
        assert mock_downloader_cls.call_count == 2

    @patch("safaribooks.core.search.search_books", new_callable=AsyncMock)
    @patch("safaribooks.core.api.ApiClient")
    def test_title_search_error_skips_gracefully(
        self,
        mock_api_client_cls: MagicMock,
        mock_search: AsyncMock,
        tmp_path: Path,
    ):
        mock_search.side_effect = SearchError("API unavailable")
        _stub_async_client(mock_api_client_cls)

        invoke_result = _invoke_fetch("some title query", output=tmp_path)
        assert invoke_result.exit_code == 1
        assert "Search error" in invoke_result.output


class TestFetchDownloadFailure:
    """Verify graceful handling when BookDownloader.run() raises."""

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_download_error(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        instance = MagicMock()
        instance.run = AsyncMock(side_effect=SafariBooksError("API exploded"))
        mock_downloader_cls.return_value = instance

        invoke_result = _invoke_fetch("9781234567890", output=tmp_path)
        assert invoke_result.exit_code == 1
        assert "Failed" in invoke_result.output
        assert "API exploded" in invoke_result.output

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_partial_failure(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        """One book fails, one succeeds — exit 0 because at least one succeeded."""
        mock_downloader_cls.side_effect = _FirstFailsFactory(tmp_path / "book2.epub")

        invoke_result = _invoke_fetch_ok(
            "9781111111111",
            "9782222222222",
            output=tmp_path,
        )
        assert "Downloaded: 1" in invoke_result.output or "Downloaded" in invoke_result.output
        assert "Failed: 1" in invoke_result.output or "Failed" in invoke_result.output


class TestFetchCLIOptions:
    """Verify that CLI options are forwarded to AppConfig correctly."""

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_image_options(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        _run_download(
            mock_downloader_cls,
            "9781234567890",
            "--image-max-size",
            str(_EXPECTED_IMAGE_MAX_SIZE),
            "--image-quality",
            str(_EXPECTED_IMAGE_QUALITY),
            output=tmp_path,
        )

        config = mock_downloader_cls.call_args[0][0]
        assert config.image_max_size == _EXPECTED_IMAGE_MAX_SIZE
        assert config.image_quality == _EXPECTED_IMAGE_QUALITY
