"""Custom XPath functions registered into lxml's default namespace."""

from typing import Any

from lxml import etree


def _xpath_lower_case(_ctx: Any, nodes: list[Any]) -> str:
    """XPath ``lower-case`` implementation operating on the first node."""
    if nodes:
        return str(nodes[0].lower())
    return ""


def register_lowercase_xpath() -> None:
    """Register a ``lower-case`` XPath function in the default namespace."""
    namespace = etree.FunctionNamespace(None)
    namespace["lower-case"] = _xpath_lower_case
