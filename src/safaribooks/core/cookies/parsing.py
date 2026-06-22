"""Cookie input parsing and normalization for O'Reilly sessions."""

import json

_OREILLY_DOMAIN = ".oreilly.com"


class _HeaderCookies:
    """Parse raw ``Cookie: k=v; k2=v2`` header strings into dicts."""

    def parse(self, header_str: str) -> dict[str, str]:
        """Parse a raw ``Cookie: k=v; k2=v2`` header string into a dict."""
        text = header_str.strip()
        if text.lower().startswith("cookie:"):
            text = text[len("cookie:") :].strip()
        if not text:
            return {}
        cookies: dict[str, str] = {}
        for raw_pair in text.split(";"):
            segment = raw_pair.strip()
            pair = self._split_pair(segment) if segment else None
            if pair is not None:
                cookies[pair[0]] = pair[1]
        return cookies

    def _split_pair(self, segment: str) -> tuple[str, str] | None:
        """Split one ``key=value`` segment into a stripped name/value tuple."""
        idx = segment.find("=")
        if idx == -1:
            return None
        name = segment[:idx].strip()
        raw_value = segment[idx + 1 :].strip()
        return name, raw_value


class _JsonCookies:
    """Parse JSON objects and browser-extension cookie arrays into dicts."""

    def from_text(self, raw: str) -> dict[str, str] | None:
        """Parse JSON cookie input, returning ``None`` when it is not JSON."""
        try:
            payload = self._decode(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

        if isinstance(payload, dict):
            return dict(payload)
        if isinstance(payload, list) and self._is_extension_array(payload):
            return self._from_extension(payload)
        return None

    def _decode(self, raw: str) -> object:
        """Decode JSON, transparently unwrapping double-encoded strings."""
        decoded = raw
        if decoded.startswith('"') and decoded.endswith('"'):
            decoded = json.loads(decoded)
        return json.loads(decoded)

    def _is_extension_array(self, payload: list[object]) -> bool:
        """Return whether the payload looks like an extension cookie array."""
        if not payload:
            return False
        first = payload[0]
        return isinstance(first, dict) and "name" in first

    def _from_extension(self, entries: list[object]) -> dict[str, str]:
        """Build a cookie dict from a browser-extension ``{name, value}`` array."""
        cookies: dict[str, str] = {}
        for entry in entries:
            if isinstance(entry, dict) and self._is_oreilly_entry(entry):
                name = str(entry["name"])
                cookies[name] = str(entry.get("value", ""))
        return cookies

    def _is_oreilly_entry(self, entry: dict[str, object]) -> bool:
        """Return whether an extension entry belongs to the O'Reilly domain."""
        if "name" not in entry:
            return False
        domain = entry.get("domain", "")
        return not domain or _OREILLY_DOMAIN in str(domain)


def normalize_cookies(cookies: dict[str, str]) -> dict[str, str]:
    """Clean and normalize a cookie dictionary."""
    return {
        name.strip(): raw_value.strip()
        for name, raw_value in cookies.items()
        if name.strip() and raw_value.strip()
    }


def parse_header(header_str: str) -> dict[str, str]:
    """Parse a raw ``Cookie:`` header string into a dict."""
    return _HeaderCookies().parse(header_str)


def parse_auto(text: str) -> dict[str, str]:
    """Auto-detect input format and return a raw cookie dict.

    Supports JSON objects, browser-extension arrays
    (``[{name, value, ...}]``), and raw ``Cookie:`` header strings.
    """
    raw = text.strip()

    from_json = _JsonCookies().from_text(raw)
    if from_json is not None:
        return from_json

    return _HeaderCookies().parse(raw)
