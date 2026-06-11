---
sidebar_position: 2
title: Configuration
description: AppConfig model fields, environment variables, and defaults.
---

# Configuration

safaribooks uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for configuration management with the `SAFARI_` environment variable prefix.

## AppConfig fields

| Field | Type | Default | Env Variable | Description |
|-------|------|---------|-------------|-------------|
| `output_dir` | `Path` | `Books/` | `SAFARI_OUTPUT_DIR` | Directory for downloaded EPUBs |
| `library_dir` | `Path` | `~/.safaribooks/` | `SAFARI_LIBRARY_DIR` | Central EPUB library |
| `rate_limit` | `float` | `1.0` | `SAFARI_RATE_LIMIT` | Requests per second |
| `rate_burst` | `int` | `2` | `SAFARI_RATE_BURST` | Token bucket burst capacity |
| `kindle` | `bool` | `false` | `SAFARI_KINDLE` | Kindle CSS optimization |
| `image_max_size` | `int` | `0` | `SAFARI_IMAGE_MAX_SIZE` | Max image dimension |
| `image_quality` | `int` | `0` | `SAFARI_IMAGE_QUALITY` | JPEG quality (1-95) |
| `ssl_skip` | `bool` | `false` | `SAFARI_SSL_SKIP` | Skip SSL verification |
| `preserve_log` | `bool` | `false` | `SAFARI_PRESERVE_LOG` | Keep log file |
| `debug` | `bool` | `false` | `SAFARI_DEBUG` | Debug logging |

## Configuration sources

Settings are loaded from (highest priority first):

1. CLI flags
2. Environment variables
3. `.env` file in the current directory
4. Default values

## Cookie storage location

Cookies are stored separately from configuration:

```
~/.config/safaribooks/cookies.json
```

The file is created with `0600` permissions (owner read/write only).

## Retry configuration

The `RetryConfig` is not user-configurable but uses these defaults:

| Parameter | API Requests | Asset Downloads |
|-----------|-------------|-----------------|
| `max_attempts` | `5` | `3` |
| `base_delay` | `1.0s` | `1.0s` |
| `max_delay` | `60.0s` | `60.0s` |
| `backoff_factor` | `2.0` | `2.0` |
| `jitter` | `0.25` | `0.25` |
