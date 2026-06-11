---
sidebar_position: 5
title: Image Quality
description: Control image dimensions and JPEG quality in downloaded EPUBs.
---

# Image Quality Settings

safaribooks can resize and compress images during download to reduce EPUB file size or match your e-reader's display.

:::warning
Image processing requires the `Pillow` library. Install it with:
```bash
uv tool install 'safaribooks[images]'
```
:::

## Maximum image size

Limit the maximum dimension (width or height) of images:

```bash
safari fetch --image-max-size 1200 9781492056348
```

- Images larger than the limit are resized proportionally
- Images smaller than the limit are not upscaled
- Set to `0` to keep original dimensions (default)

## JPEG quality

Control JPEG compression quality:

```bash
safari fetch --image-quality 80 9781492056348
```

- Values range from `1` (lowest quality, smallest file) to `95` (highest quality, largest file)
- Set to `0` to keep original quality (default)
- Only affects JPEG images; PNGs and other formats are not recompressed

## Combining both options

```bash
safari fetch --image-max-size 800 --image-quality 70 9781492056348
```

This is useful for e-ink devices where high-resolution images provide no visible benefit but increase file size.

## Recommended settings

| Use case | `--image-max-size` | `--image-quality` |
|----------|-------------------|-------------------|
| Desktop/tablet reading | `0` (default) | `0` (default) |
| Kindle/e-ink | `800` | `75` |
| Minimal file size | `600` | `60` |
| Archival quality | `0` | `0` |
