"""Markdown text escaping and backtick-fence escalation helpers."""

import re

_BACKTICK_RUN_RE = re.compile(r"`+")
_MIN_FENCE = 3
_BACKTICK = "`"


def escape_text(text: str) -> str:
    """Escape the few characters that would otherwise break inline Markdown."""
    return text.replace("\\", r"\\").replace(_BACKTICK, r"\`")


def _longest_backtick_run(text: str) -> int:
    """Return the length of the longest backtick run within *text*."""
    return max((len(run) for run in _BACKTICK_RUN_RE.findall(text)), default=0)


def code_span(text: str) -> str:
    """Render an inline code span with backtick-fence escalation."""
    longest = _longest_backtick_run(text)
    ticks = _BACKTICK * (longest + 1)
    needs_pad = bool(longest) or text.startswith(_BACKTICK) or text.endswith(_BACKTICK)
    pad = " " if needs_pad else ""
    return f"{ticks}{pad}{text}{pad}{ticks}"


def fence_for(code: str) -> str:
    """Return a backtick fence long enough to wrap *code*."""
    longest = _longest_backtick_run(code)
    return _BACKTICK * max(_MIN_FENCE, longest + 1)
