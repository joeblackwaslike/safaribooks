---
sidebar_position: 4
title: Image Problems
description: Troubleshoot image download and processing issues.
---

# Image Problems

Issues with images in downloaded EPUBs and how to resolve them.

## Missing images in EPUB

**Symptom:** Images show as broken or blank in the EPUB reader.

**Cause:** The image URL returned a 404 or the CDN was temporarily unavailable.

**Fix:** Re-run the download. safaribooks logs which assets failed. If specific images consistently fail, they may have been removed from O'Reilly's CDN.

## Image resize flags have no effect

**Symptom:** `--image-max-size` and `--image-quality` flags are ignored.

**Cause:** The `Pillow` library is not installed. Image processing requires Pillow, and the flags are silently ignored without it.

**Fix:**
```bash
# If installed via uv
uv tool install 'safaribooks[images]'

# If installed via pip
pip install 'safaribooks[images]'

# Or install Pillow directly
pip install Pillow
```

Verify Pillow is available:

```bash
python -c "from PIL import Image; print('Pillow OK')"
```

## Images are too large / EPUB file too big

**Symptom:** EPUB file is very large (50MB+), mostly due to high-resolution images.

**Fix:** Use image optimization flags:

```bash
safari fetch --image-max-size 800 --image-quality 75 9781492056348
```

See the [Image Quality guide](../guides/image-quality.md) for recommended settings per device.

## Images look blurry after resize

**Symptom:** Images are pixelated or blurry in the EPUB.

**Cause:** `--image-max-size` is set too low for your display.

**Fix:** Increase the max size or remove the flag:

```bash
# Higher resolution
safari fetch --image-max-size 1200 9781492056348

# Original quality (no resize)
safari fetch 9781492056348
```

## Cover image missing

**Symptom:** EPUB opens without a cover image.

**Cause:** The book's cover URL returned an error, or the book metadata doesn't include a cover reference.

**Fix:** Re-run the download. If the cover is consistently missing, the O'Reilly listing may not have a cover image configured for this book.
