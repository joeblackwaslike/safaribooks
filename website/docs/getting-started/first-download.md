---
sidebar_position: 4
title: First Download
description: Download your first O'Reilly book as EPUB.
---

# Your First Download

This page walks you through downloading a book end-to-end.

## Step 1: Find the book ID

Every O'Reilly book has an identifier in its URL. For example:

```
https://learning.oreilly.com/library/view/fluent-python-2nd/9781492056348/
                                                              ^^^^^^^^^^^^^
                                                              This is the book ID
```

The book ID is `9781492056348`.

## Step 2: Run the download

```bash
safari fetch 9781492056348
```

You'll see progress output as safaribooks:

1. Authenticates with your stored cookies
2. Fetches book metadata from the O'Reilly API
3. Downloads all chapters
4. Downloads CSS, images, fonts, and videos in parallel
5. Packages everything into an EPUB file

## Step 3: Find your EPUB

By default, the EPUB is saved to:

```
Books/Fluent Python 2nd Edition.epub
```

The output directory defaults to `Books/` in the current working directory. Change it with `--output`:

```bash
safari fetch 9781492056348 --output ~/my-books/
```

## Step 4: Open the book

Open the EPUB in your preferred reader:

- **macOS**: Apple Books (double-click the file)
- **Linux**: Calibre, Foliate
- **Windows**: Calibre, Sumatra PDF
- **Kindle**: Convert with `ebook-convert` first (see [Kindle optimization](../guides/kindle-optimization.md))

## Using a URL instead

You can pass the full O'Reilly URL instead of extracting the ID:

```bash
safari fetch "https://learning.oreilly.com/library/view/fluent-python-2nd/9781492056348/"
```

## Searching by title

Don't have the URL? Search by title:

```bash
safari fetch "Fluent Python"
```

safaribooks will search O'Reilly and present matching results for you to select from.

## Next steps

- [Download multiple books](../guides/downloading-books.md)
- [Download playlists](../guides/playlists.md)
- [CLI reference](../reference/cli-commands.md) for all options
