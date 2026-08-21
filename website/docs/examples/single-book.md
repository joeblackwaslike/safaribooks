---
sidebar_position: 1
title: Single Book
description: Download a single book by ID.
---

# Download a Single Book

The simplest use case: download one book by its O'Reilly ID.

## Find the book ID

Go to the book on O'Reilly and grab the ID from the URL:

```
https://learning.oreilly.com/library/view/fluent-python-2nd/9781492056348/
```

The book ID is `9781492056348`.

## Download it

```bash
safari fetch 9781492056348
```

## Expected output

```
Authenticating...
Fetching book info for 9781492056348...
  Title: Fluent Python, 2nd Edition
  Authors: Luciano Ramalho
  Chapters: 38

Downloading chapters...
  [1/38] Preface
  [2/38] Chapter 1. The Python Data Model
  ...
  [38/38] Index

Downloading assets...
  CSS: 3 files
  Images: 47 files
  Fonts: 2 files

Building EPUB...
Done: Books/Fluent Python 2nd Edition.epub
```

## Custom output directory

```bash
safari fetch 9781492056348 --output ~/my-books/
```

The EPUB will be saved as `~/my-books/Fluent Python 2nd Edition.epub`.
