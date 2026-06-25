"""YAML scalar quoting for single-line front-matter values."""

_NEEDS_QUOTING = frozenset(":#'\"\n[]{},*&!|>%@`")


def yaml_inline_string(raw: str) -> str:
    """Quote *raw* for safe single-line YAML output."""
    if _needs_quoting(raw):
        escaped = raw.replace("\\", r"\\").replace('"', r"\"")
        return f'"{escaped}"'
    return raw


def _needs_quoting(raw: str) -> bool:
    """Return ``True`` when *raw* cannot be emitted as a bare YAML scalar."""
    if not raw or raw != raw.strip():
        return True
    return any(token in raw for token in _NEEDS_QUOTING)
