"""Rewrite footnote-reference identifiers throughout the block IR.

Footnote ids are namespaced per chapter (``c{index}-{id}``) so references stay
unique once chapters are merged into one document; these helpers thread the
``old -> new`` mapping recursively through blocks, list items, tables, and inline
runs.
"""

from dataclasses import replace

from safaribooks.core.markdown import ir

Mapping = dict[str, str]
Inlines = tuple[ir.Inline, ...]
Cells = tuple[ir.TableCell, ...]


def rewrite_inlines(nodes: Inlines, mapping: Mapping) -> Inlines:
    """Rewrite footnote-reference identifiers within an inline sequence."""
    return tuple(_rewrite_inline(node, mapping) for node in nodes)


def _rewrite_inline(node: ir.Inline, mapping: Mapping) -> ir.Inline:
    """Rewrite a single inline node's footnote identifier (recursively)."""
    if isinstance(node, ir.FootnoteRef):
        return ir.FootnoteRef(mapping.get(node.identifier, node.identifier))
    if isinstance(node, (ir.Emphasis, ir.Strong, ir.Link)):
        return replace(node, children=rewrite_inlines(node.children, mapping))
    return node


def rewrite_block(block: ir.Block, mapping: Mapping) -> ir.Block:
    """Rewrite footnote identifiers within a block (recursively)."""
    if isinstance(block, (ir.Paragraph, ir.Heading)):
        return replace(block, children=rewrite_inlines(block.children, mapping))
    if isinstance(block, (ir.BlockQuote, ir.FootnoteDef)):
        children = tuple(rewrite_block(child, mapping) for child in block.children)
        return replace(block, children=children)
    if isinstance(block, ir.ListBlock):
        rewritten = tuple(_rewrite_item(list_item, mapping) for list_item in block.items)
        return replace(block, items=rewritten)
    if isinstance(block, ir.Table):
        return _rewrite_table(block, mapping)
    return block


def _rewrite_item(list_item: ir.ListItem, mapping: Mapping) -> ir.ListItem:
    """Rewrite footnote identifiers within a list item."""
    return ir.ListItem(tuple(rewrite_block(child, mapping) for child in list_item.children))


def _rewrite_cells(cells: Cells, mapping: Mapping) -> Cells:
    """Rewrite footnote identifiers within a row of table cells."""
    return tuple(ir.TableCell(rewrite_inlines(cell.children, mapping)) for cell in cells)


def _rewrite_table(block: ir.Table, mapping: Mapping) -> ir.Table:
    """Rewrite footnote identifiers within table cells."""
    header = None if block.header is None else _rewrite_cells(block.header, mapping)
    rows = tuple(_rewrite_cells(row, mapping) for row in block.rows)
    return ir.Table(header=header, rows=rows)
