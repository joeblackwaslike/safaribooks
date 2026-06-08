# Plan: Merge Image Quality & Apple Books Fixes

## Context

The safaribooks fork (on `feat/migrate-api-v2`) has several known image issues: low-resolution cover thumbnails, duplicate cover pages when books already include a cover chapter, Apple Books not displaying cover art in the library view, and no ability to resize/compress oversized images. Five upstream PRs address these in different ways — we need the optimal non-conflicting subset adapted to our v2-migrated codebase.

## PR Triage

| PR | Title | Verdict | Reason |
|----|-------|---------|--------|
| **#332** | Make cover art show in Apple Books library | **MERGE** | Essential 6-line fix — OPF `<meta name="cover">` must reference a manifest item ID, not a filename |
| **#364** | Improve cover image quality + fix duplicate cover | **MERGE** | HD cover URL fallback chain + duplicate cover prevention |
| **#120** | Support resize image and change image quality | **MERGE** | Unique feature — Pillow-based resize/compress via CLI args |
| #203 | Use Higher Resolution image of Book Cover | **SKIP** | Massive refactor (101 lines changed) that overlaps with #364's HD cover logic and would conflict heavily with our v2 API migration |
| #114 | Optimisation for Books app | **SKIP** | Superseded by #332; also has a Python logic bug (`if 'cover.' or 'Cover.' or 'titlepage.' in i` is always truthy) |

The three selected PRs touch different functions with no overlap:
- **#332** → `create_content_opf()` (OPF metadata)
- **#364** → `get_default_cover()` + `__init__` cover-insertion block
- **#120** → `_thread_download_images()` + new `_resize_image()` + CLI args

## Implementation

### 1. Apple Books cover meta fix (from PR #332)

**File:** `safaribooks.py` — `create_content_opf()` (lines 1120-1166)

The OPF template at line 288 has `<meta name="cover" content="{8}"/>` where `{8}` is `self.cover`. Currently `self.cover` holds a filename like `default_cover.jpg` or `Images/cover.jpg`, but Apple Books requires it to reference a manifest `<item id="...">`.

**Change:** In `create_content_opf()`, before the `return` statement, derive the cover's manifest item ID from `self.cover` using the same `img_` prefix pattern used when building manifest entries (line 1136). Pass that ID instead of `self.cover` as `{8}`.

```python
# Derive cover manifest ID to match <item id="img_..."> entries
cover_id = self.cover
if cover_id:
    match = re.search(r'/(\w+)\.', cover_id)
    if match is not None:
        cover_id = "img_" + match.group(1)
```

Then pass `cover_id` instead of `self.cover` as position 8 in the format call.

### 2. HD cover image + duplicate cover prevention (from PR #364)

**File:** `safaribooks.py` — two locations

#### 2a. `get_default_cover()` (line 766)

Replace the single URL attempt with a fallback chain trying HD variants first:

```python
def get_default_cover(self):
    cover_url = self.book_info["cover"]
    hd_url_attempts = [
        cover_url.replace("/thumb/", "/orig/"),
        cover_url.replace("/thumb/", "/"),
        cover_url.replace("thumbnail", "cover"),
        cover_url,  # fallback to original
    ]
    response = None
    for url in hd_url_attempts:
        response = self.requests_provider(url, stream=True)
        if response != 0 and response.status_code == 200:
            self.display.log("Retrieved HD cover from: %s" % url)
            break
    if response == 0 or response.status_code != 200:
        self.display.error("Error trying to retrieve the cover: %s" % cover_url)
        return False
    # ... rest unchanged (file_ext extraction, write chunks, return filename)
```

#### 2b. `__init__` cover-insertion block (lines 398-412)

Wrap the default cover creation in a check for existing cover chapters:

```python
if not self.cover:
    has_cover_chapter = any(
        "cover" in ch.get("filename", "").lower() or "cover" in ch.get("title", "").lower()
        for ch in self.book_chapters
    )
    if not has_cover_chapter and "cover" in self.book_info:
        self.cover = self.get_default_cover()
        if self.cover:
            cover_html = self.parse_html(
                html.fromstring('<div id="sbo-rt-content"><img src="Images/{0}"></div>'.format(self.cover)), True
            )
            self.book_chapters = [{"filename": "default_cover.xhtml", "title": "Cover"}] + self.book_chapters
            self.filename = self.book_chapters[0]["filename"]
            self.save_page_html(cover_html)
```

### 3. Image resize/quality CLI options (from PR #120)

**Files:** `safaribooks.py`, `requirements.txt`

#### 3a. Add Pillow to requirements.txt

```
Pillow
```

#### 3b. Conditional import at top of safaribooks.py

```python
try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
```

#### 3c. New `_resize_image()` method

Add after `_thread_download_images()`:

```python
def _resize_image(self, image_path):
    if not HAS_PILLOW:
        return
    max_size = self.args.image_max_size
    quality = self.args.image_quality
    if max_size == 0 and quality == 0:
        return
    try:
        image = Image.open(image_path)
        if max_size > 0:
            image.thumbnail((max_size, max_size))
        if quality > 0:
            image.save(image_path, quality=quality)
        else:
            image.save(image_path)
    except Exception:
        pass  # skip unprocessable images (e.g. corrupt, unsupported format)
```

#### 3d. Call `_resize_image()` in `_thread_download_images()` after writing the file (line 1082)

After the `with open(image_path, 'wb')` block, add:
```python
self._resize_image(image_path)
```

#### 3e. Two new CLI arguments in the argparse section

```python
arguments.add_argument(
    "--image-max-size", dest="image_max_size", type=int, default=0,
    help="Resize images if width/height exceeds this value (0 = no resize). Requires Pillow."
)
arguments.add_argument(
    "--image-quality", dest="image_quality", type=int, default=0,
    help="JPEG compression quality 1-95 (0 = keep original). Requires Pillow."
)
```

## Verification

1. **Syntax check:** `python3 -c "import safaribooks"` — no import errors
2. **Pillow optional:** Running without Pillow installed should work (just no resize)
3. **OPF validation:** After building an EPUB, inspect `content.opf` — the `<meta name="cover" content="..."/>` should contain an `img_*` ID that matches a `<item id="img_*">` in the manifest
4. **Cover quality:** Compare cover image file size before/after — HD URLs should yield larger files
5. **No duplicate covers:** Books that already have a cover chapter shouldn't get a second `default_cover.xhtml`
6. **Apple Books:** Open a generated EPUB in Apple Books — cover should display in library grid view
