---
sidebar_position: 1
title: Downloading Books
description: Download books by ID, URL, title search, or from a file.
---

# Downloading Books

safaribooks supports several ways to specify which books to download.

## By book ID

Pass one or more book IDs as positional arguments:

```bash
safari fetch 9781492056348
```

## By O'Reilly URL

Pass the full URL from your browser:

```bash
safari fetch "https://learning.oreilly.com/library/view/fluent-python-2nd/9781492056348/"
```

## Multiple books

Pass multiple IDs or URLs in a single command:

```bash
safari fetch 9781492056348 9781098150518 9781492051367
```

Books are downloaded sequentially in the order specified.

## From a file

Create a text file with one book ID per line:

```text title="books.txt"
9781492056348
9781098150518
9781492051367
```

```bash
safari fetch --file books.txt
```

Lines starting with `#` are treated as comments and skipped.

## By title search

Pass a search term and safaribooks will query the O'Reilly API:

```bash
safari fetch "Fluent Python"
```

When multiple results match, you'll see an interactive selection prompt:

```
Search results for "Fluent Python":
  [1] Fluent Python, 2nd Edition — Luciano Ramalho (9781492056348)
  [2] Fluent Python — Luciano Ramalho (9781491946008)
Select a book (1-2):
```

## Combining options

You can combine IDs, URLs, and file-based input:

```bash
safari fetch 9781492056348 --file more-books.txt --output ~/library/
```

## Output options

| Flag | Description | Default |
|------|-------------|---------|
| `--output` / `-o` | Output directory for EPUB files | `Books/` |
| `--library-dir` | Central EPUB library directory | `~/.safaribooks/` |
| `--preserve-log` | Keep log file even without errors | `false` |
