"""Cookie extraction, parsing, validation, and persistence for O'Reilly sessions."""


import json
import logging
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from safaribooks.core.constants import BROWSER_JS, REQUIRED_COOKIES
from safaribooks.core.exceptions import CookieError
from safaribooks.core.models import CookieSet

logger = logging.getLogger(__name__)

# Supported browsers for automatic cookie extraction.
_SUPPORTED_BROWSERS = ("chrome", "firefox", "edge", "chromium")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_cookies(cookies: dict[str, str]) -> dict[str, str]:
    """Strip whitespace from keys/values and drop empty entries."""
    return {k.strip(): v.strip() for k, v in cookies.items() if k.strip() and v.strip()}


def _parse_header(header_str: str) -> dict[str, str]:
    """Parse a raw ``Cookie: k=v; k2=v2`` header string into a dict."""
    text = header_str.strip()
    if text.lower().startswith("cookie:"):
        text = text[len("cookie:") :].strip()
    if not text:
        return {}
    cookies: dict[str, str] = {}
    for raw_pair in text.split(";"):
        segment = raw_pair.strip()
        if not segment:
            continue
        idx = segment.find("=")
        if idx == -1:
            continue
        cookies[segment[:idx].strip()] = segment[idx + 1 :].strip()
    return cookies


def _parse_auto(text: str) -> dict[str, str]:
    """Auto-detect input format and return a cookie dict.

    Supports JSON objects, browser-extension arrays (``[{name, value, ...}]``),
    and raw ``Cookie:`` header strings.
    """
    raw = text.strip()

    # Try JSON first (handles double-encoded strings too).
    try:
        decoded = raw
        if decoded.startswith('"') and decoded.endswith('"'):
            decoded = json.loads(decoded)
        data = json.loads(decoded)

        if isinstance(data, dict):
            return dict(data)

        if isinstance(data, list) and data and isinstance(data[0], dict) and "name" in data[0]:
            return {
                c["name"]: c.get("value", "")
                for c in data
                if isinstance(c, dict)
                and "name" in c
                and (not c.get("domain") or ".oreilly.com" in c.get("domain", ""))
            }
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Fall back to raw cookie header string.
    return _parse_header(raw)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_cookies(cookies: dict[str, str]) -> dict[str, str]:
    """Clean and normalize a cookie dictionary."""
    return _normalize_cookies(cookies)


def parse_auto(text: str) -> dict[str, str]:
    """Auto-detect input format and return a raw cookie dict."""
    return _parse_auto(text)


def parse_header(header_str: str) -> dict[str, str]:
    """Parse a raw ``Cookie:`` header string into a dict."""
    return _parse_header(header_str)


def from_browser(browser_name: str) -> CookieSet:
    """Extract cookies from an installed browser via *browser_cookie3*."""
    try:
        import browser_cookie3  # noqa: PLC0415
    except ImportError:
        msg = (
            "browser_cookie3 is not installed. "
            "Install the optional dependency with: uv pip install 'safaribooks[browser]'"
        )
        raise CookieError(msg) from None

    browsers = {
        "chrome": browser_cookie3.chrome,
        "firefox": browser_cookie3.firefox,
        "edge": browser_cookie3.edge,
        "chromium": browser_cookie3.chromium,
    }
    if browser_name not in browsers:
        msg = f"Unsupported browser {browser_name!r}. Choose from: {', '.join(sorted(browsers))}"
        raise CookieError(msg)

    try:
        cookie_jar = browsers[browser_name](domain_name=".oreilly.com")
    except Exception as exc:
        msg = (
            f"Failed to extract cookies from {browser_name}: {exc}\n"
            "Make sure the browser is closed and try again, or use paste mode instead."
        )
        raise CookieError(msg) from exc

    raw = _normalize_cookies({c.name: c.value for c in cookie_jar})
    return validate(raw)


def from_paste() -> CookieSet:
    """Interactively read pasted cookies from stdin and return a validated set."""
    console = Console(stderr=True)
    console.print(
        "[bold]Paste cookies from your browser, then press Enter on an empty line to finish.[/]"
    )
    console.print("  Accepted formats:")
    console.print(f"    - JSON from console:  [dim]{BROWSER_JS.splitlines()[-1]}[/]")
    console.print("    - Raw Cookie header:  [dim]Cookie: k1=v1; k2=v2[/]")
    console.print('    - Extension export:   [dim][{"name":"k","value":"v",...}, ...][/]')
    console.print()

    lines: list[str] = []
    while True:
        try:
            line = Prompt.ask("[green]>[/]" if not lines else "[green] [/]")
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)

    raw = "\n".join(lines).strip()
    if not raw:
        raise CookieError("Empty input — no cookies provided.")

    cookies = _parse_auto(raw)
    if not cookies:
        raise CookieError("Could not parse input. Check that you copied the full output.")

    cookies = _normalize_cookies(cookies)
    return validate(cookies)


def from_file(path: Path) -> CookieSet:
    """Load cookies from a JSON file on disk."""
    path = Path(path)
    if not path.is_file():
        raise CookieError(f"Cookie file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    cookies = _parse_auto(raw)
    if not cookies:
        raise CookieError(
            "Could not parse cookie file. "
            "Expected a JSON dict, browser-extension array, or cookie header string."
        )

    cookies = _normalize_cookies(cookies)
    return validate(cookies)


def from_header(header_str: str) -> CookieSet:
    """Parse a raw ``Cookie:`` header string and return a validated cookie set."""
    cookies = _parse_header(header_str)
    if not cookies:
        raise CookieError("Could not parse cookie header string.")

    cookies = _normalize_cookies(cookies)
    return validate(cookies)


def validate(cookies: dict[str, str]) -> CookieSet:
    """Validate a raw cookie dict and return a ``CookieSet``."""
    if not cookies:
        raise CookieError("No cookies provided.")

    # Log soft warnings before hard validation.
    if len(cookies) < 3:
        logger.warning(
            "Only %d cookie(s) found — extraction may be incomplete.",
            len(cookies),
        )

    empty_keys = [k for k, v in cookies.items() if not v]
    if empty_keys:
        logger.warning("Empty values for cookies: %s", ", ".join(empty_keys))

    try:
        return CookieSet(cookies=cookies)
    except ValueError as exc:
        missing = REQUIRED_COOKIES - cookies.keys()
        msg = f"Missing required cookies: {', '.join(sorted(missing))}" if missing else str(exc)
        raise CookieError(msg) from exc


def save(cookies: CookieSet, output: Path) -> None:
    """Write a validated cookie set to a JSON file with restricted permissions."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(cookies.cookies, indent=2) + "\n", encoding="utf-8")
    try:
        output.chmod(0o600)
    except OSError:
        logger.debug("Could not set permissions on %s", output)

    logger.info("Saved %d cookies to %s", len(cookies.cookies), output)
