---
sidebar_position: 1
title: CLI Commands
description: Complete CLI reference for the safari command.
---

# CLI Commands

safaribooks provides the `safari` CLI with two main subcommands: `fetch` and `auth`.

## Root command

```bash
safari [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--version` / `-v` | Show version and exit |
| `--debug` | Enable debug logging |

---

## safari fetch

Download books as EPUB files.

```bash
safari fetch [OPTIONS] [BOOK_IDS]...
```

### Positional arguments

| Argument | Description |
|----------|-------------|
| `BOOK_IDS` | One or more book IDs, O'Reilly URLs, or title search terms |

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--playlist` / `-p` | `UUID` | -- | Download all books from a playlist |
| `--file` / `-f` | `path` | -- | File with book IDs, one per line |
| `--kindle` | `bool` | `false` | Add Kindle-compatible CSS |
| `--output` / `-o` | `path` | `Books/` | Output directory |
| `--library-dir` | `path` | `~/.safaribooks/` | Central EPUB library directory |
| `--rate-limit` / `-r` | `float` | `1.0` | Max requests per second |
| `--rate-burst` | `int` | `2` | Burst capacity for rate limiter |
| `--image-max-size` | `int` | `0` | Max image dimension (0 = no resize) |
| `--image-quality` | `int` | `0` | JPEG quality 1-95 (0 = keep original) |
| `--ssl-skip` | `bool` | `false` | Skip SSL verification |
| `--preserve-log` | `bool` | `false` | Keep log file even without errors |

### Examples

```bash
# Single book by ID
safari fetch 9781492056348

# Multiple books
safari fetch 9781492056348 9781098150518

# From URL
safari fetch "https://learning.oreilly.com/library/view/fluent-python-2nd/9781492056348/"

# By title search
safari fetch "Fluent Python"

# From file with custom output
safari fetch --file books.txt --output ~/library/

# Playlist with Kindle optimization
safari fetch --playlist d4f2c4a8-... --kindle

# With rate limit and image settings
safari fetch --rate-limit 0.5 --image-max-size 800 --image-quality 75 9781492056348
```

:::tip
You can combine `--file`, `--playlist`, and positional `BOOK_IDS` in a single command. All sources are merged.
:::

---

## safari auth

Manage authentication cookies.

### safari auth setup

Interactive guided setup for cookie extraction.

```bash
safari auth setup
```

### safari auth extract

Extract cookies directly from a browser's cookie store.

```bash
safari auth extract [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--browser` | `string` | -- | Browser to extract from: `chrome`, `firefox`, `edge`, `chromium` |

```bash
safari auth extract --browser chrome
```

### safari auth import

Import cookies from a header string or file.

```bash
safari auth import [OPTIONS]
```

| Flag | Type | Description |
|------|------|-------------|
| `--header` | `string` | Cookie header string (from DevTools) |
| `--file` | `path` | Path to JSON cookie file |

```bash
# From header string
safari auth import --header "groot_sessionid=abc; jwt=eyJ...; csrf_access_token=xyz; logged_in=y"

# From file
safari auth import --file cookies.json
```

:::warning
Provide either `--header` or `--file`, not both.
:::

### safari auth validate

Check that stored cookies are valid by making a test API call.

```bash
safari auth validate
```

### safari auth status

Show current authentication status and cookie expiry info.

```bash
safari auth status
```
