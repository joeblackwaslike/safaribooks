---
sidebar_position: 5
title: Custom Image Settings
description: Control image dimensions and quality in downloaded EPUBs.
---

# Custom Image Settings

Resize and compress images to reduce EPUB file size or match your reader's display.

## Resize images

Limit all images to a maximum dimension of 800 pixels:

```bash
safari fetch --image-max-size 800 9781492056348
```

Images larger than 800px (width or height) are scaled down proportionally. Smaller images are left untouched.

## Set JPEG quality

Compress JPEG images to 75% quality:

```bash
safari fetch --image-quality 75 9781492056348
```

## Combine both

For e-ink readers, reduce both size and quality:

```bash
safari fetch --image-max-size 800 --image-quality 70 9781492056348
```

## Practical comparison

| Settings | Typical EPUB size | Best for |
|----------|------------------|----------|
| Default (no flags) | ~15 MB | Desktop/tablet |
| `--image-max-size 800 --image-quality 75` | ~8 MB | E-ink readers |
| `--image-max-size 600 --image-quality 60` | ~5 MB | Minimal storage |

:::warning
Image processing requires the `Pillow` library. If it's not installed, these flags are silently ignored. Install with:
```bash
uv tool install 'safaribooks[images]'
```
:::
