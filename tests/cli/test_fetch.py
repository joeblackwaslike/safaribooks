"""Tests for the ``safari fetch`` CLI command."""


from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from safaribooks.cli import app
from safaribooks.core.exceptions import ApiError, SafariBooksError, SearchError
from safaribooks.core.models import SearchResponse, SearchResult

runner = CliRunner()


class TestFetchHelp:
    """Verify the fetch command surfaces all expected options."""

    def test_fetch_help_shows_options(self):
        result = runner.invoke(app, ["fetch", "--help"])
        assert result.exit_code == 0
        assert "book-ids" in result.output.lower() or "BOOK_IDS" in result.output
        assert "--playlist" in result.output
        assert "--file" in result.output
        assert "--kindle" in result.output
        assert "--output" in result.output
        assert "--image-max-size" in result.output
        assert "--image-quality" in result.output
        assert "--ssl-skip" in result.output
        assert "--preserve-log" in result.output


class TestFetchNoArgs:
    """Verify fetch fails when no book IDs are provided."""

    def test_fetch_no_args_shows_error(self):
        result = runner.invoke(app, ["fetch"])
        assert result.exit_code == 1
        assert "Provide book IDs" in result.output or "Error" in result.output


class TestFetchWithBookId:
    """Verify fetch invokes BookDownloader with the correct book ID."""

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_single_book_id(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=tmp_path / "test_book.epub")
        mock_downloader_cls.return_value = mock_instance

        result = runner.invoke(app, ["fetch", "9781234567890", "--output", str(tmp_path)])
        assert result.exit_code == 0
        assert "Downloading 1 book(s)" in result.output

        mock_downloader_cls.assert_called_once()
        call_kwargs = mock_downloader_cls.call_args
        assert call_kwargs[0][1] == "9781234567890"  # positional: config, book_id

        mock_instance.run.assert_called_once()

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_multiple_book_ids(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=tmp_path / "book.epub")
        mock_downloader_cls.return_value = mock_instance

        result = runner.invoke(
            app,
            ["fetch", "9781111111111", "9782222222222", "--output", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Downloading 2 book(s)" in result.output
        assert mock_downloader_cls.call_count == 2

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_url_input(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        """Verifies that a full O'Reilly URL is normalized to a bare book ID."""
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=tmp_path / "book.epub")
        mock_downloader_cls.return_value = mock_instance

        result = runner.invoke(
            app,
            [
                "fetch",
                "https://learning.oreilly.com/library/view/-/9781234567890/",
                "--output",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
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

        # Make ApiClient work as an async context manager
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_api_client_cls.return_value = mock_client

        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=tmp_path / "book.epub")
        mock_downloader_cls.return_value = mock_instance

        result = runner.invoke(
            app,
            ["fetch", "--playlist", "some-playlist-uuid", "--output", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Fetching playlist" in result.output
        assert "Found 2 books" in result.output
        assert "Downloading 2 book(s)" in result.output

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

        # Make ApiClient work as an async context manager
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_api_client_cls.return_value = mock_client

        result = runner.invoke(
            app,
            ["fetch", "--playlist", "bad-uuid", "--output", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "Error" in result.output


class TestFetchWithFile:
    """Verify fetch reads book IDs from a file."""

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_from_file(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        ids_file = tmp_path / "book_ids.txt"
        ids_file.write_text("9781111111111\n9782222222222\n\n9783333333333\n", encoding="utf-8")

        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=tmp_path / "book.epub")
        mock_downloader_cls.return_value = mock_instance

        result = runner.invoke(
            app,
            ["fetch", "--file", str(ids_file), "--output", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Downloading 3 book(s)" in result.output
        assert mock_downloader_cls.call_count == 3

    def test_fetch_from_missing_file(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.txt"
        result = runner.invoke(
            app,
            ["fetch", "--file", str(missing), "--output", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "Error" in result.output

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_from_file_with_urls(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        """IDs file with a mix of bare IDs and URLs."""
        ids_file = tmp_path / "ids.txt"
        ids_file.write_text(
            "9781111111111\nhttps://learning.oreilly.com/library/view/-/9782222222222/\n",
            encoding="utf-8",
        )

        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=tmp_path / "book.epub")
        mock_downloader_cls.return_value = mock_instance

        result = runner.invoke(
            app,
            ["fetch", "--file", str(ids_file), "--output", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Downloading 2 book(s)" in result.output


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

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_api_client_cls.return_value = mock_client

        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=tmp_path / "book.epub")
        mock_downloader_cls.return_value = mock_instance

        result = runner.invoke(
            app,
            ["fetch", "Python Crash Course", "--output", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Searching for" in result.output
        assert "Downloading 1 book(s)" in result.output
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

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_api_client_cls.return_value = mock_client

        result = runner.invoke(
            app,
            ["fetch", "nonexistent book xyz", "--output", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "No books found" in result.output

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

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_api_client_cls.return_value = mock_client

        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=tmp_path / "book.epub")
        mock_downloader_cls.return_value = mock_instance

        result = runner.invoke(
            app,
            ["fetch", "9781234567890", "Learning Go", "--output", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Downloading 2 book(s)" in result.output
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

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_api_client_cls.return_value = mock_client

        result = runner.invoke(
            app,
            ["fetch", "some title query", "--output", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "Search error" in result.output


class TestFetchDownloadFailure:
    """Verify graceful handling when BookDownloader.run() raises."""

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_download_error(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(side_effect=SafariBooksError("API exploded"))
        mock_downloader_cls.return_value = mock_instance

        result = runner.invoke(
            app,
            ["fetch", "9781234567890", "--output", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "Failed" in result.output
        assert "API exploded" in result.output

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_fetch_partial_failure(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        """One book fails, one succeeds — exit 0 because at least one succeeded."""
        call_count = 0

        def make_instance(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            inst = MagicMock()
            if call_count == 1:
                inst.run = AsyncMock(side_effect=SafariBooksError("Failed first"))
            else:
                inst.run = AsyncMock(return_value=tmp_path / "book2.epub")
            return inst

        mock_downloader_cls.side_effect = make_instance

        result = runner.invoke(
            app,
            ["fetch", "9781111111111", "9782222222222", "--output", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "Downloaded: 1" in result.output or "Downloaded" in result.output
        assert "Failed: 1" in result.output or "Failed" in result.output


class TestFetchCLIOptions:
    """Verify that CLI options are forwarded to AppConfig correctly."""

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_kindle_option(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=tmp_path / "book.epub")
        mock_downloader_cls.return_value = mock_instance

        result = runner.invoke(
            app,
            ["fetch", "9781234567890", "--kindle", "--output", str(tmp_path)],
        )
        assert result.exit_code == 0

        config = mock_downloader_cls.call_args[0][0]
        assert config.kindle is True

    @patch("safaribooks.cli.fetch.BookDownloader")
    def test_image_options(self, mock_downloader_cls: MagicMock, tmp_path: Path):
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=tmp_path / "book.epub")
        mock_downloader_cls.return_value = mock_instance

        result = runner.invoke(
            app,
            [
                "fetch",
                "9781234567890",
                "--image-max-size",
                "800",
                "--image-quality",
                "85",
                "--output",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0

        config = mock_downloader_cls.call_args[0][0]
        assert config.image_max_size == 800
        assert config.image_quality == 85
