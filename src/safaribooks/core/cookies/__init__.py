"""Cookie extraction, parsing, validation, and persistence for O'Reilly sessions.

This package exposes a flat public API re-exported from its concern-based
submodules so that callers continue to use ``from safaribooks.core.cookies
import ...`` unchanged.
"""

from pathlib import Path

from rich.prompt import Prompt

from safaribooks.core.cookies.parsing import (
    normalize_cookies,
    parse_auto,
    parse_header,
)
from safaribooks.core.cookies.persistence import save, validate
from safaribooks.core.cookies.sources import (  # noqa: WPS347 (public re-export surface)
    from_browser,
    from_file,
    from_header,
    from_paste,
)
from safaribooks.core.models import CookieSet

__all__ = (  # noqa: WPS410, WPS412 (intentional public-API declaration)
    "CookieSet",
    "Path",
    "Prompt",
    "from_browser",
    "from_file",
    "from_header",
    "from_paste",
    "normalize_cookies",
    "parse_auto",
    "parse_header",
    "save",
    "validate",
)
