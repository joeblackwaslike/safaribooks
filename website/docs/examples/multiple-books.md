---
sidebar_position: 2
title: Multiple Books
description: Download multiple books in one command.
---

# Download Multiple Books

Pass multiple book IDs in a single command to download them sequentially.

## By IDs

```bash
safari fetch 9781492056348 9781098150518 9781492051367
```

Books are downloaded one at a time in the order specified.

## From a file

Create a text file with one ID per line:

```text title="books.txt"
# Python books
9781492056348
9781098150518

# Go books
9781492051367
```

```bash
safari fetch --file books.txt
```

Lines starting with `#` are comments. Blank lines are skipped.

## Mixed sources

Combine positional IDs, file input, and playlists:

```bash
safari fetch 9781492056348 --file more-books.txt --playlist d4f2c4a8-...
```

## With shared options

Apply options to all books in the batch:

```bash
safari fetch --file books.txt --kindle --output ~/library/ --rate-limit 0.5
```

:::tip
For large batches, use a lower `--rate-limit` (e.g., `0.5`) to reduce the chance of session expiry mid-download.
:::
