"""Cookie loaders: browser extraction, interactive paste, file, and header."""

from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from safaribooks.core.constants import BROWSER_JS
from safaribooks.core.cookies.parsing import normalize_cookies, parse_auto, parse_header
from safaribooks.core.cookies.persistence import validate
from safaribooks.core.exceptions import CookieError
from safaribooks.core.models import CookieSet


class _BrowserExtractor:
    """Extract O'Reilly cookies from an installed browser via *browser_cookie3*."""

    def extract(self, browser_name: str) -> dict[str, str]:
        """Return normalized cookies pulled from the named browser."""
        loaders = self._loaders()
        if browser_name not in loaders:
            choices = ", ".join(sorted(loaders))
            msg = f"Unsupported browser {browser_name!r}. Choose from: {choices}"
            raise CookieError(msg)

        try:
            cookie_jar = loaders[browser_name](domain_name=".oreilly.com")
        except Exception as exc:
            msg = (
                f"Failed to extract cookies from {browser_name}: {exc}\n"
                "Make sure the browser is closed and try again, or use paste mode instead."
            )
            raise CookieError(msg) from exc

        return normalize_cookies({cookie.name: cookie.value for cookie in cookie_jar})

    def _loaders(self) -> dict[str, object]:
        """Return the supported ``browser_cookie3`` loader callables."""
        try:
            import browser_cookie3  # noqa: PLC0415 (optional dependency, imported lazily)
        except ImportError:
            msg = (
                "browser_cookie3 is not installed. "
                "Install the optional dependency with: uv pip install 'safaribooks[browser]'"
            )
            raise CookieError(msg) from None

        return {
            "chrome": browser_cookie3.chrome,
            "firefox": browser_cookie3.firefox,
            "edge": browser_cookie3.edge,
            "chromium": browser_cookie3.chromium,
        }


class _PasteReader:
    """Interactively read pasted cookies from stdin."""

    def read(self) -> str:
        """Print instructions, collect pasted lines, and return the raw text."""
        console = Console(stderr=True)
        self._print_instructions(console)
        return "\n".join(self._read_lines()).strip()

    def _print_instructions(self, console: Console) -> None:
        """Print the accepted cookie input formats to the given console."""
        console.print(
            "[bold]Paste cookies from your browser, then press Enter on an empty line to finish.[/]"
        )
        console.print("  Accepted formats:")
        json_example = BROWSER_JS.splitlines()[-1]
        console.print(f"    - JSON from console:  [dim]{json_example}[/]")
        console.print("    - Raw Cookie header:  [dim]Cookie: k1=v1; k2=v2[/]")
        console.print('    - Extension export:   [dim][{"name":"k","value":"v",...}, ...][/]')
        console.print()

    def _read_lines(self) -> list[str]:
        """Read lines from stdin until an empty line or EOF is encountered."""
        lines: list[str] = []
        while True:
            prompt = "[green] [/]" if lines else "[green]>[/]"
            try:
                line = Prompt.ask(prompt)
            except EOFError:
                break
            if not line.strip():
                break
            lines.append(line)
        return lines


def from_browser(browser_name: str) -> CookieSet:
    """Extract cookies from an installed browser via *browser_cookie3*."""
    raw = _BrowserExtractor().extract(browser_name)
    return validate(raw)


def from_paste() -> CookieSet:
    """Interactively read pasted cookies from stdin and return a validated set."""
    raw = _PasteReader().read()
    if not raw:
        raise CookieError("Empty input — no cookies provided.")

    cookies = parse_auto(raw)
    if not cookies:
        raise CookieError("Could not parse input. Check that you copied the full output.")

    return validate(normalize_cookies(cookies))


def from_file(path: Path) -> CookieSet:
    """Load cookies from a JSON file on disk."""
    path = Path(path)
    if not path.is_file():
        raise CookieError(f"Cookie file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    cookies = parse_auto(raw)
    if not cookies:
        raise CookieError(
            "Could not parse cookie file. "
            "Expected a JSON dict, browser-extension array, or cookie header string."
        )

    return validate(normalize_cookies(cookies))


def from_header(header_str: str) -> CookieSet:
    """Parse a raw ``Cookie:`` header string and return a validated cookie set."""
    cookies = parse_header(header_str)
    if not cookies:
        raise CookieError("Could not parse cookie header string.")

    return validate(normalize_cookies(cookies))
