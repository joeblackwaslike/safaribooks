"""Font reference scanning in CSS and sequential font downloading."""

import logging
import re
from collections.abc import Callable
from pathlib import Path

from safaribooks.core.api import ApiClient
from safaribooks.core.assets.download import _HTTP_OK
from safaribooks.core.constants import SAFARI_BASE_URL

logger = logging.getLogger(__name__)

_FONT_URL_RE = re.compile(r"url\(['\"]?([^)]*\.(?:otf|ttf|woff|woff2))['\"]?\)")

_REMOTE_FONT_PREFIXES = ("data:", "http://", "https://")

_FONT_FILES_URL_TEMPLATE = "{base}/api/v2/epubs/urn:orm:book:{book_id}/files/{font}"


class _FontDownloader:
    """Scan CSS for font references and fetch them sequentially."""

    def __init__(
        self,
        client: ApiClient,
        css_dir: Path,
        book_id: str,
        *,
        progress_callback: Callable[[int, int], None] | None,
    ) -> None:
        self._client = client
        self._css_dir = css_dir
        self._book_id = book_id
        self._progress_callback = progress_callback
        self._total = 0
        self._completed = 0

    def scan(self) -> set[str]:
        """Scan every ``.css`` file in the directory for local font references."""
        font_urls: set[str] = set()
        for css_file in self._css_dir.iterdir():
            if css_file.suffix != ".css":
                continue
            css_text = self._read_css(css_file)
            if css_text is not None:
                font_urls.update(self._extract_local(css_text))
        return font_urls

    async def fetch_all(self, font_urls: set[str]) -> list[str]:
        """Download every font sequentially, reporting progress per font."""
        downloaded: list[str] = []
        self._total = len(font_urls)
        self._completed = 0
        pending = iter(sorted(font_urls))
        font_name = next(pending, None)
        while font_name is not None:
            basename = await self._step(font_name)
            if basename is not None:
                downloaded.append(basename)
            font_name = next(pending, None)
        return downloaded

    async def _step(self, font_name: str) -> str | None:
        """Fetch one font and report progress regardless of the outcome."""
        basename = await self._fetch_one(font_name)
        self._completed += 1
        if self._progress_callback is not None:
            self._progress_callback(self._total, self._completed)
        return basename

    def _read_css(self, css_file: Path) -> str | None:
        """Read a CSS file, returning ``None`` (with a warning) if unreadable."""
        try:
            return css_file.read_text(errors="ignore")
        except OSError:
            logger.warning(
                "Could not read CSS file for font scanning: %s",
                css_file,
                exc_info=True,
            )
            return None

    def _extract_local(self, css_text: str) -> set[str]:
        """Return local (non-remote, non-data) font names in *css_text*."""
        found: set[str] = set()
        for match in _FONT_URL_RE.finditer(css_text):
            font_name = match.group(1).strip("'\"")
            if not font_name.startswith(_REMOTE_FONT_PREFIXES):
                found.add(font_name)
        return found

    async def _fetch_one(self, font_name: str) -> str | None:
        """Download a single font, returning its basename or ``None``."""
        basename = Path(font_name).name
        font_path = self._css_dir / basename

        if font_path.is_file():
            logger.debug("Font already exists, skipping: %s", basename)
            return basename

        url = _FONT_FILES_URL_TEMPLATE.format(
            base=SAFARI_BASE_URL,
            book_id=self._book_id,
            font=font_name,
        )
        try:
            response = await self._client.get(url)
        except Exception:
            logger.exception("Error downloading font: %s", font_name)
            return None

        if response.status_code != _HTTP_OK:
            logger.error("HTTP %d downloading font: %s", response.status_code, font_name)
            return None

        font_path.write_bytes(response.content)
        return basename


async def download_fonts(
    client: ApiClient,
    css_dir: Path,
    book_id: str,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[str]:
    """Parse CSS files for font references and download them.

    Scans every ``.css`` file in *css_dir* for ``url()`` references to
    font files (otf, ttf, woff, woff2), then downloads them from the
    O'Reilly files API.

    Parameters
    ----------
    client:
        Authenticated API client.
    css_dir:
        The ``Styles/`` directory containing CSS files.
    book_id:
        Book identifier for the files API URL.
    progress_callback:
        Optional ``(total, completed)`` progress callback.

    Returns:
    -------
    list[str]
        Filenames of successfully downloaded font files.

    """
    if not css_dir.is_dir():
        return []

    downloader = _FontDownloader(
        client,
        css_dir,
        book_id,
        progress_callback=progress_callback,
    )
    font_urls = downloader.scan()
    if not font_urls:
        return []

    logger.info("Found %d font references in CSS files", len(font_urls))
    return await downloader.fetch_all(font_urls)
