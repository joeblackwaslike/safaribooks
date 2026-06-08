# Migrate safaribooks from O'Reilly API v1 to v2

## Context

O'Reilly's v1 API (`/api/v1/book/{id}/`) now returns 404 for all books, breaking the tool completely. Five upstream PRs propose fixes. After reviewing all of them, the best approach cherry-picks from three:

- **PR #379** (wraymo) — foundation: cleanest diff, iterative chapter pagination (fixes RecursionError on 700+ chapter books), `normalize_toc()`, tested on 9 real books
- **PR #377** (sohailnajar) — metadata enrichment: search API for authors/publishers, `unquote()` fix for URL-encoded filenames, redirect-following on login check
- **PR #370** (frozenprocess) — error handling: `parse_json_response()` helper with detailed diagnostics

PRs #371 and #356 are skipped (#371 has syntax errors; #356 is orthogonal Kindle/encoding fixes, not a v2 migration).

## Architecture: Adapter at the API Boundary

All v2 responses are transformed into the exact v1 shapes at the API layer. Downstream code (EPUB generation, HTML parsing, image/CSS download, TOC creation) requires **zero changes**. Three adapter methods do all the work:
- `get_book_info()` + `_enrich_book_metadata()` — book metadata
- `get_book_chapters()` + `_normalize_chapter()` — chapter list
- `create_toc()` + `normalize_toc()` — table of contents

## Files to Modify

- [safaribooks.py](safaribooks.py) — all API changes
- [retrieve_cookies.py](retrieve_cookies.py) — full rewrite with two modes
- [README.md](README.md) — updated auth instructions + cookie guide

## Changes (in implementation order)

### 1. Imports & Constants

- Add `unquote` to `urllib.parse` imports (line 18)
- Change `API_TEMPLATE` from v1 to v2: `SAFARI_BASE_URL + "/api/v2/epubs/urn:orm:book:{0}/"`
- Add `CHAPTERS_API_TEMPLATE`: `SAFARI_BASE_URL + "/api/v2/epub-chapters/?epub_identifier=urn:orm:book:{0}"`
- Add `SEARCH_API_TEMPLATE`: `SAFARI_BASE_URL + "/api/v2/search/?query={0}&limit=1&formats=book"`
- Add `FILES_API_TEMPLATE`: `SAFARI_BASE_URL + "/api/v2/epubs/urn:orm:book:{0}/files/"`
- Update User-Agent from Chrome 90 → Chrome 124

### 2. New Helper Methods (standalone, no behavior change)

**`parse_json_response(response, context)`** — from PR #370. Returns parsed JSON or `None` with proper handling for non-JSON responses, bad status codes, and parse failures.

**`_normalize_chapter(v2_chapter)`** — transforms a single v2 chapter into v1-compatible dict:
- `unquote()` on filename (fixes URL-encoding bug from PR #377)
- Sets `asset_base_url` to `FILES_API_TEMPLATE` (eliminates ad-hoc v2 detection in `get()`)
- Normalizes `images` and `stylesheets` from either top-level or `related_assets` nesting
- Stylesheets converted from `[str]` → `[{url: str}]` to match v1 `x["url"]` access pattern

**`normalize_toc(v2_toc, depth)`** — from PR #379. Recursively converts v2 TOC entries (`{url, label, id, children}`) into v1 shape (`{depth, fragment, id, label, href, children}`). Applies `unquote()` to `href`.

### 3. Rewrite API Methods

**`check_login()`** — remove `perform_redirect=False` so profile page redirect is followed (from PR #377)

**`get_book_info()`** — fetch v2 endpoint, map fields to v1-compatible dict (title, isbn, description, web_url, rights, cover from `cover_url`), then call `_enrich_book_metadata()`

**`_enrich_book_metadata(book_info)`** — from PR #377. Calls search API to fill in `authors`, `publishers`, `subjects`, `issued`. Wraps in try/except so failure is non-fatal (EPUB still created with empty fields).

**`get_book_chapters()`** — from PR #379. Iterative `while chapters_url:` loop with `data.get("next")` pagination. Each result passed through `_normalize_chapter()`. Cover chapters moved to front.

**`create_toc()`** — URL changes to `self.api_url + "table-of-contents/"`. Response passed through `normalize_toc()` before `parse_toc()`.

### 4. Simplify Downstream Code

- **`get()` method (lines 815-826):** Remove `api_v2_detected` logic. Image URLs: use directly if absolute, else join with `asset_base_url`.
- **`__init__` (lines 353-354):** Remove `sys.setrecursionlimit()` hack — iterative pagination eliminates the need.
- **`api_error()`:** Add guards for non-dict responses and missing cookies file.

### 5. Rewrite retrieve_cookies.py (from PR #377)

The current script blindly dumps ALL browser cookies and requires `browser_cookie3` as a hard dependency. Replace with PR #377's two-mode approach:

**Mode 1: Paste from console (default, zero dependencies)**
- Print a JS one-liner for the user to run in their browser console on `learning.oreilly.com`
- User pastes the JSON output, script saves to `cookies.json`
- Handles double-encoded strings gracefully

**Mode 2: Browser auto-extract (`--browser chrome|firefox|edge|chromium`)**
- Uses `browser_cookie3` (optional dependency, only needed for this mode)
- Filters to `.oreilly.com` domain only (privacy fix + smaller request headers)
- Supports Chrome, Firefox, Edge, Chromium

Add argparse CLI: `python retrieve_cookies.py --paste` (default) or `python retrieve_cookies.py -b chrome`

### 6. Update README.md

The README is severely outdated — it still advertises `--cred` login as the primary flow and barely mentions `cookies.json`. Rewrite the auth/usage sections:

**Replace the "Attention needed" banner** with a clear status: v2 API migration complete, cookie-based auth only.

**Rewrite the Usage section** to lead with the cookie workflow:
1. Log in to `https://learning.oreilly.com` in your browser
2. Get cookies (two options presented equally):
   - **Quick way:** Open browser console → paste JS one-liner → save output as `cookies.json`
   - **Script way:** `python retrieve_cookies.py` (prompts you to paste) or `python retrieve_cookies.py -b chrome` (auto-extracts)
3. Run: `python3 safaribooks.py <BOOK_ID>`

**Include the JS snippet** (from PR #373) directly in the README:
```javascript
JSON.stringify(document.cookie.split(';').reduce((o,c) => {
  let [k,v] = c.trim().split('='); o[k] = v; return o;
}, {}))
```

**Remove/de-emphasize** the `--cred` and `--login` options from the help output and examples — they're dead code. Keep them in argparse for a deprecation warning but don't feature them in docs.

**Update the program options block** to reflect current reality (cookie-based auth only).

**Clean up dead commented-out code** in the `__main__` block (lines 1104-1122) that handled the old `--cred` flow.

## Data Contracts (what adapter methods must produce)

```
book_info: {title, identifier, isbn, description, web_url, rights, cover, issued,
            authors: [{name}], publishers: [{name}], subjects: [{name}]}

chapter:   {filename, title, content (URL), asset_base_url,
            images: [str], stylesheets: [{url}], site_styles: [str]}

toc_entry: {depth, fragment, id, label, href, children: [recursive]}
```

## Verification

1. Run with a known book ID: `python safaribooks.py <BOOK_ID>` with valid `cookies.json`
2. Verify EPUB opens in Calibre and converts to AZW3
3. Check: metadata (authors, title, publisher) present in OPF
4. Check: TOC navigation works (links resolve to correct chapters)
5. Check: images and CSS render correctly
6. Test with a large book (700+ chapters) to verify no RecursionError
