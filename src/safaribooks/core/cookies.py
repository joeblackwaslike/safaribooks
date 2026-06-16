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

# File mode granting read/write to the owner only.
_OWNER_ONLY_MODE = 0o600

# Domain fragment used to filter browser-extension cookie exports.
_OREILLY_DOMAIN = ".oreilly.com"

# Below this count a cookie set is likely an incomplete extraction.
_MIN_EXPECTED_COOKIES = 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_cookies(cookies: dict[str, str]) -> dict[str, str]:
    """Strip whitespace from keys/values and drop empty entries."""
    return {
        name.strip(): raw_value.strip()
        for name, raw_value in cookies.items()
        if name.strip() and raw_value.strip()
    }


def _split_pair(segment: str) -> tuple[str, str] | None:
    """Split one ``key=value`` segment into a stripped name/value tuple."""
    idx = segment.find("=")
    if idx == -1:
        return None
    name = segment[:idx].strip()
    raw_value = segment[idx + 1 :].strip()
    return name, raw_value


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
        pair = _split_pair(segment) if segment else None
        if pair is not None:
            cookies[pair[0]] = pair[1]
    return cookies


def _decode_json(raw: str) -> object:
    """Decode JSON, transparently unwrapping double-encoded strings."""
    decoded = raw
    if decoded.startswith('"') and decoded.endswith('"'):
        decoded = json.loads(decoded)
    return json.loads(decoded)


def _is_oreilly_entry(entry: dict[str, object]) -> bool:
    """Return whether an extension entry belongs to the O'Reilly domain."""
    if "name" not in entry:
        return False
    domain = entry.get("domain", "")
    return not domain or _OREILLY_DOMAIN in str(domain)


def _cookies_from_extension(entries: list[object]) -> dict[str, str]:
    """Build a cookie dict from a browser-extension ``{name, value}`` array."""
    cookies: dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, dict) and _is_oreilly_entry(entry):
            name = str(entry["name"])
            cookies[name] = str(entry.get("value", ""))
    return cookies


def _is_extension_array(payload: list[object]) -> bool:
    """Return whether the payload looks like an extension cookie array."""
    if not payload:
        return False
    first = payload[0]
    return isinstance(first, dict) and "name" in first


def _cookies_from_json(raw: str) -> dict[str, str] | None:
    """Parse JSON cookie input, returning ``None`` when it is not JSON."""
    try:
        payload = _decode_json(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None

    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, list) and _is_extension_array(payload):
        return _cookies_from_extension(payload)
    return None


def _parse_auto(text: str) -> dict[str, str]:
    """Auto-detect input format and return a cookie dict.

    Supports JSON objects, browser-extension arrays
    (``[{name, value, ...}]``), and raw ``Cookie:`` header strings.
    """
    raw = text.strip()

    # Try JSON first (handles double-encoded strings too).
    from_json = _cookies_from_json(raw)
    if from_json is not None:
        return from_json

    # Fall back to raw cookie header string.
    return _parse_header(raw)


def _print_paste_instructions(console: Console) -> None:
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


def _read_pasted_lines() -> list[str]:
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
        import browser_cookie3
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
        choices = ", ".join(sorted(browsers))
        msg = f"Unsupported browser {browser_name!r}. Choose from: {choices}"
        raise CookieError(msg)

    try:
        cookie_jar = browsers[browser_name](domain_name=".oreilly.com")
    except Exception as exc:
        msg = (
            f"Failed to extract cookies from {browser_name}: {exc}\n"
            "Make sure the browser is closed and try again, or use paste mode instead."
        )
        raise CookieError(msg) from exc

    raw = _normalize_cookies({cookie.name: cookie.value for cookie in cookie_jar})
    return validate(raw)


def from_paste() -> CookieSet:
    """Interactively read pasted cookies from stdin and return a validated set."""
    console = Console(stderr=True)
    _print_paste_instructions(console)

    lines = _read_pasted_lines()
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


def _warn_on_suspicious_cookies(cookies: dict[str, str]) -> None:
    """Emit soft warnings for sparse or empty-valued cookie dicts."""
    if len(cookies) < _MIN_EXPECTED_COOKIES:
        logger.warning(
            "Only %d cookie(s) found — extraction may be incomplete.",
            len(cookies),
        )

    empty_keys = [name for name, cookie_value in cookies.items() if not cookie_value]
    if empty_keys:
        logger.warning("Empty values for cookies: %s", ", ".join(empty_keys))


def _validation_error_message(cookies: dict[str, str], exc: ValueError) -> str:
    """Build a user-facing message for a failed ``CookieSet`` validation."""
    missing = REQUIRED_COOKIES - cookies.keys()
    if missing:
        missing_names = ", ".join(sorted(missing))
        return f"Missing required cookies: {missing_names}"
    return str(exc)


def validate(cookies: dict[str, str]) -> CookieSet:
    """Validate a raw cookie dict and return a ``CookieSet``."""
    if not cookies:
        raise CookieError("No cookies provided.")

    # Log soft warnings before hard validation.
    _warn_on_suspicious_cookies(cookies)

    try:
        return CookieSet(cookies=cookies)
    except ValueError as exc:
        raise CookieError(_validation_error_message(cookies, exc)) from exc


def save(cookies: CookieSet, output: Path) -> None:
    """Write a validated cookie set to a JSON file with restricted permissions."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = f"{json.dumps(cookies.cookies, indent=2)}\n"
    output.write_text(payload, encoding="utf-8")
    try:
        output.chmod(_OWNER_ONLY_MODE)
    except OSError:
        logger.debug("Could not set permissions on %s", output)

    logger.info("Saved %d cookies to %s", len(cookies.cookies), output)
