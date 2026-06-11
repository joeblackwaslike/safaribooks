---
sidebar_position: 4
title: Kindle Optimization
description: Optimize EPUBs for Kindle e-readers.
---

# Kindle Optimization

The `--kindle` flag adds CSS rules that improve readability on Kindle devices and other e-ink readers.

## What it does

When `--kindle` is enabled, safaribooks injects CSS rules that:

- Set `overflow: hidden` on pre-formatted code blocks to prevent horizontal scrolling
- Adjust table layouts for narrow e-ink screens
- Apply word-wrap rules for long lines of code

## Usage

```bash
safari fetch --kindle 9781492056348
```

## Converting EPUB to Kindle format

Kindle devices natively read AZW3 format. Use Calibre's `ebook-convert` to convert:

```bash
# Convert to AZW3 (recommended for Kindle)
ebook-convert "Fluent Python 2nd Edition.epub" "Fluent Python 2nd Edition.azw3"

# Convert to MOBI (legacy Kindle format)
ebook-convert "Fluent Python 2nd Edition.epub" "Fluent Python 2nd Edition.mobi"
```

:::tip
Install Calibre from [calibre-ebook.com](https://calibre-ebook.com/) to get the `ebook-convert` command-line tool.
:::

## Send to Kindle

After conversion, send the AZW3 file to your Kindle via:

1. **USB**: Connect your Kindle and copy the file to the `documents` folder
2. **Email**: Send as an attachment to your `@kindle.com` address
3. **Send to Kindle app**: Use Amazon's [Send to Kindle](https://www.amazon.com/sendtokindle) service

:::info
Amazon's Send to Kindle service now accepts EPUB files directly, so you may not need to convert at all.
:::
