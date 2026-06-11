---
sidebar_position: 6
title: Title Search
description: Search for books by title and download interactively.
---

# Title Search

Don't have the book ID? Search by title and select from the results.

## Search and download

```bash
safari fetch "Fluent Python"
```

## Interactive selection

When multiple books match, you'll see a selection prompt:

```
Search results for "Fluent Python":
  [1] Fluent Python, 2nd Edition — Luciano Ramalho (9781492056348)
  [2] Fluent Python — Luciano Ramalho (9781491946008)
Select a book (1-2): 1
```

Type the number and press Enter. The selected book is then downloaded.

## Tips for effective searches

| Search term | Results |
|------------|---------|
| `"Fluent Python"` | Books with "Fluent Python" in the title |
| `"Python Data Science"` | Broader match across Python data science titles |
| `"9781492056348"` | Direct ID lookup (skips search, downloads immediately) |

:::tip
If you already know the book ID or have the URL, pass it directly to skip the search step:
```bash
safari fetch 9781492056348
safari fetch "https://learning.oreilly.com/library/view/fluent-python-2nd/9781492056348/"
```
:::

## Combining search with other books

You can mix search terms with explicit IDs:

```bash
safari fetch "Fluent Python" 9781098150518
```

The search results prompt appears for the search term, while the explicit ID downloads immediately.
