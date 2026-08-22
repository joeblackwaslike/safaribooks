"""Functional helpers for rewriting inline nodes throughout the block IR.

Extensions use :func:`map_inlines` to apply an inline-level transform (which may
drop or expand nodes) across an entire chapter's blocks, recursing into nested
containers. The transform receives each inline node *after* its children have
already been mapped.
"""

from collections.abc import Callable
from dataclasses import replace

from safaribooks.core.markdown import ir

InlineFn = Callable[[ir.Inline], list[ir.Inline]]
Blocks = tuple[ir.Block, ...]
Inlines = tuple[ir.Inline, ...]


def map_inlines(blocks: Blocks, transform: InlineFn) -> Blocks:
    """Apply *transform* to every inline node within *blocks*, returning new blocks."""
    return tuple(_map_block(block, transform) for block in blocks)


def _map_block(block: ir.Block, transform: InlineFn) -> ir.Block:
    """Apply *transform* to the inline content of a single block (recursively)."""
    if isinstance(block, (ir.Paragraph, ir.Heading)):
        return replace(block, children=_map_inline_seq(block.children, transform))
    if isinstance(block, ir.Table):
        return _map_table(block, transform)
    return _map_container(block, transform)


def _map_container(block: ir.Block, transform: InlineFn) -> ir.Block:
    """Apply *transform* within nesting-block containers (quote/def/list)."""
    if isinstance(block, (ir.BlockQuote, ir.FootnoteDef)):
        mapped = tuple(_map_block(child, transform) for child in block.children)
        return replace(block, children=mapped)
    if isinstance(block, ir.ListBlock):
        mapped_items = tuple(_map_item(list_item, transform) for list_item in block.items)
        return replace(block, items=mapped_items)
    return block


def _map_item(list_item: ir.ListItem, transform: InlineFn) -> ir.ListItem:
    """Apply *transform* within a list item's blocks."""
    return ir.ListItem(tuple(_map_block(child, transform) for child in list_item.children))


def _map_cells(
    cells: tuple[ir.TableCell, ...],
    transform: InlineFn,
) -> tuple[ir.TableCell, ...]:
    """Apply *transform* within a row of table cells."""
    return tuple(ir.TableCell(_map_inline_seq(cell.children, transform)) for cell in cells)


def _map_table(block: ir.Table, transform: InlineFn) -> ir.Table:
    """Apply *transform* within table cells."""
    header = None if block.header is None else _map_cells(block.header, transform)
    rows = tuple(_map_cells(row, transform) for row in block.rows)
    return ir.Table(header=header, rows=rows)


def _map_inline_seq(nodes: Inlines, transform: InlineFn) -> Inlines:
    """Map *transform* over an inline sequence, recursing into containers first."""
    mapped: list[ir.Inline] = []
    for node in nodes:
        if isinstance(node, (ir.Emphasis, ir.Strong, ir.Link)):
            recursed = replace(node, children=_map_inline_seq(node.children, transform))
            mapped.extend(transform(recursed))
        else:
            mapped.extend(transform(node))
    return tuple(mapped)
