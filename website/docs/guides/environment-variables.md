---
sidebar_position: 6
title: Environment Variables
description: Configure safaribooks with environment variables.
---

# Environment Variables

All safaribooks settings can be configured via environment variables with the `SAFARI_` prefix.

## Available variables

| Variable | CLI Flag | Type | Default | Description |
|----------|----------|------|---------|-------------|
| `SAFARI_OUTPUT_DIR` | `--output` | `path` | `Books/` | Output directory for EPUBs |
| `SAFARI_LIBRARY_DIR` | `--library-dir` | `path` | `~/.safaribooks/` | Central EPUB library |
| `SAFARI_RATE_LIMIT` | `--rate-limit` | `float` | `1.0` | Max requests per second |
| `SAFARI_RATE_BURST` | `--rate-burst` | `int` | `2` | Burst capacity |
| `SAFARI_KINDLE` | `--kindle` | `bool` | `false` | Add Kindle-compatible CSS |
| `SAFARI_IMAGE_MAX_SIZE` | `--image-max-size` | `int` | `0` | Max image dimension (0=no resize) |
| `SAFARI_IMAGE_QUALITY` | `--image-quality` | `int` | `0` | JPEG quality 1-95 (0=original) |
| `SAFARI_SSL_SKIP` | `--ssl-skip` | `bool` | `false` | Skip SSL verification |
| `SAFARI_PRESERVE_LOG` | `--preserve-log` | `bool` | `false` | Keep log file even without errors |
| `SAFARI_DEBUG` | `--debug` | `bool` | `false` | Enable debug logging |

## Using a `.env` file

Create a `.env` file in the directory where you run safaribooks:

```bash title=".env"
SAFARI_OUTPUT_DIR=~/my-books
SAFARI_RATE_LIMIT=0.5
SAFARI_KINDLE=true
SAFARI_IMAGE_MAX_SIZE=800
SAFARI_IMAGE_QUALITY=75
```

safaribooks uses pydantic-settings, which loads `.env` files automatically.

## Precedence

Settings are resolved in this order (highest wins):

1. **CLI flags** -- `--rate-limit 2.0`
2. **Environment variables** -- `SAFARI_RATE_LIMIT=2.0`
3. **`.env` file** -- `SAFARI_RATE_LIMIT=2.0`
4. **Default values**

:::tip
For persistent settings, use a `.env` file. For one-off overrides, use CLI flags.
:::
