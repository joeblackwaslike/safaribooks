"""Infer the language of a code block from class hints."""

import re

from lxml import html

_LANG_CLASS_RE = re.compile(r"(?:language|highlight|brush:|lang)[-:\s]([\w+-]+)")


def code_language(pre: html.HtmlElement) -> str:  # type: ignore[no-any-unimported]
    """Infer the code language from class hints on ``<pre>`` or inner ``<code>``."""
    candidates = [pre.get("class", "")]
    code = pre.find(".//code")
    if code is not None:
        candidates.append(code.get("class", ""))
    for class_value in candidates:
        match = _LANG_CLASS_RE.search(class_value)
        if match:
            return match.group(1)
    return ""
