# Upstream PR Evaluation & Implementation Plan

## Context

We maintain a fork of `lorenzodifuccia/safaribooks` that has been migrated to the O'Reilly API v2 with cookie-based authentication (branch `feat/migrate-api-v2`). The upstream repo has 17 open PRs with various improvements. This plan evaluates each, votes on which to adopt, and sequences implementation to avoid incompatibilities.

---

## PR Evaluations

### ADOPT (10 PRs)

| # | PR | Title | Type | Rationale |
|---|-----|-------|------|-----------|
| 1 | [#165](https://github.com/lorenzodifuccia/safaribooks/pull/165) | Don't write CSS if download failed | **Critical bug fix** | Lines 1076-1081: after CSS download fails (`response == 0`), code continues to `response.content` which crashes. One-line `return` fix. |
| 2 | [#308](https://github.com/lorenzodifuccia/safaribooks/pull/308) | Reduce false positives in link_replace | Bug fix | Lines 833-837: `any(x in link for x in ["cover", "images", "graphics"])` matches HTML page links containing these substrings (e.g. `Images/ch08.xhtml#sec-ggg`). Fix: only apply image keywords when link is not an HTML page. |
| 3 | [#347](https://github.com/lorenzodifuccia/safaribooks/pull/347) | Non-HTML root page parsing | Bug fix | Some chapters lack `<html>` root tags, causing parse failures. Adds html5lib fallback. Small, targeted fix for issue #335. |
| 4 | [#276](https://github.com/lorenzodifuccia/safaribooks/pull/276) | Extract book ID from URL | QoL | Users paste full URLs like `https://learning.oreilly.com/.../9781491958698/` instead of just the digits. Regex extraction prevents OSError on Windows. |
| 5 | [#343](https://github.com/lorenzodifuccia/safaribooks/pull/343) | Font downloading for non-English books | Feature | Non-English books reference `.otf` fonts in CSS. Adds `collect_fonts()` mirroring the existing CSS/image download pattern. Important for i18n. |
| 6 | [#354](https://github.com/lorenzodifuccia/safaribooks/pull/354) | Download books from playlists | Feature | `--playlist` flag queries collections API, filters for books only, downloads sequentially. Useful batch feature. |
| 7 | [#89](https://github.com/lorenzodifuccia/safaribooks/pull/89) | Multiple book IDs | Feature (concept) | Allow multiple positional book IDs. Take concept only — actual code has whitespace churn and v1 API assumptions. Combine with #354's playlist logic. |
| 8 | [#204](https://github.com/lorenzodifuccia/safaribooks/pull/204) | Asyncio parallel downloads | Performance | Replace dead multiprocessing code (commented out at lines 1148-1163) with asyncio. Solves cross-platform issues (SSL/Windows/macOS). Reported 30min→12min on image-heavy books. |
| 9 | [#365](https://github.com/lorenzodifuccia/safaribooks/pull/365) | Video/MP4 support | Feature | Download embedded MP4 video clips into EPUB. Extends image download pattern. Related to issue #140. |
| 10 | [#342](https://github.com/lorenzodifuccia/safaribooks/pull/342) | Dockerfile | DevOps | Minimal Docker approach. Needs updates: Python 3.11+, remove `--cred` example, add cookie volume mount. |

### PARTIAL ADOPT (2 PRs — cherry-pick specific pieces)

| # | PR | Title | What to take | What to skip |
|---|-----|-------|--------------|--------------|
| 11 | [#372](https://github.com/lorenzodifuccia/safaribooks/pull/372) | Improve error handling | `--ssl-skip` CLI flag | JSON/status-code checks — already handled by our `parse_json_response()` and existing guard clauses |
| 12 | [#166](https://github.com/lorenzodifuccia/safaribooks/pull/166) | Print raw response on error | Pattern: include `response.text` in unexpected API errors | Login-specific code — login is deprecated in our fork |

### REJECT (5 PRs)

| # | PR | Title | Reason |
|---|-----|-------|--------|
| 13 | [#207](https://github.com/lorenzodifuccia/safaribooks/pull/207) | Download all books in a topic | **Breaking change**: converts positional `bookid` to named arg. Topic downloads are too broad (could download hundreds of books). Overlap with #354 for batch use cases. |
| 14 | [#325](https://github.com/lorenzodifuccia/safaribooks/pull/325) | BeautifulSoup for M1 ARM | Heavy workaround (adds `beautifulsoup4` dep). M1 lxml issues resolved in newer versions. PR #347's html5lib fallback is lighter and more targeted. |
| 15 | [#320](https://github.com/lorenzodifuccia/safaribooks/pull/320) | Fix staticmethod crash | Method `fix_overconstrained_images` doesn't exist in our codebase. PR was against a different fork state with unrelated commits mixed in. |
| 16 | [#68](https://github.com/lorenzodifuccia/safaribooks/pull/68) | Dockerize (2019) | Superseded by #342 which has a cleaner approach. |
| 17 | [#25](https://github.com/lorenzodifuccia/safaribooks/pull/25) | Dockerfile (2018) | Superseded by #342. Maintainer declined original. |

---

## Implementation Plan

### Phase 1: Bug Fixes (low risk, high value)

**Commit 1 — PR #165: CSS download crash fix**
- File: `safaribooks.py` ~line 1078
- Add `return` after the error log when `response == 0` in `_thread_download_css()`
- Prevents crash from accessing `.content` on a `0` value

**Commit 2 — PR #308: link_replace false positives**
- File: `safaribooks.py` ~lines 830-847
- Add `is_html_link()` static method (check if suffix is `.html`/`.xhtml`/`.htm`)
- Add `is_image_implied()` static method (the `["cover", "images", "graphics"]` check)
- Refactor `link_replace()` to only apply image-keyword matching when link is NOT an HTML link
- Preserves the existing `is_image_link()` check for actual image extensions

**Commit 3 — PR #347: Non-HTML root page fallback**
- File: `safaribooks.py` — `get_html()` method
- File: `requirements.txt` — add `html5lib>=1.1`
- After `html.fromstring()`, check if response lacks `<html` tag
- If so, re-parse with `html.html5parser.fromstring()` to wrap content properly
- Fallback only — doesn't change behavior for well-formed HTML

**Commit 4 — PR #276: Book ID extraction from URL**
- File: `safaribooks.py` — main block, before `SafariBooks(args_parsed)`
- Add regex to extract numeric ID from full O'Reilly URLs
- Pattern: `https?://.*?/(\d{10,15})/?` and bare `(\d{10,15})`
- Mutate `args_parsed.bookid` to the extracted ID
- Error if no valid ID found

### Phase 2: Error Handling & SSL (low risk)

**Commit 5 — PR #372 (partial): SSL-skip flag**
- File: `safaribooks.py` — arg parsing + session setup
- Add `--ssl-skip` argument
- When set, configure `self.session.verify = False` and suppress urllib3 InsecureRequestWarning
- Useful for corporate proxies with MITM certificates

**Commit 6 — PR #166 (pattern): Raw response in errors**
- File: `safaribooks.py` — `parse_json_response()` and `api_error()`
- When JSON parsing fails or API returns unexpected response, include truncated `response.text[:500]` in error output
- Aids debugging without requiring `--preserve-log`

### Phase 3: Download Improvements (medium risk)

**Commit 7 — PR #204: Asyncio parallel downloads**
- File: `safaribooks.py`
- Add `import asyncio`
- Replace `_start_multiprocessing()` with `_start_parallel_download()` using `asyncio.get_event_loop()` + `run_in_executor()`
- Update `collect_css()` and `collect_images()` to use the new async method
- Remove dead `_start_multiprocessing()` code and `WinQueue` if present
- Keep progress tracking via queues

**Commit 8 — PR #343: Font downloading**
- File: `safaribooks.py`
- Add `self.fonts = []` and `self.fonts_done_queue` initialization
- Add `collect_fonts()` method: scan CSS files for `url(*.otf)` patterns, download from v2 API
- Call `collect_fonts()` between `collect_css()` and `collect_images()` in the main flow
- Include fonts in EPUB manifest with appropriate media types

### Phase 4: New Features (higher risk, test carefully)

**Commit 9 — PRs #89 + #354: Multiple book IDs + playlist support**
- File: `safaribooks.py` — arg parsing and main block
- Change `bookid` positional arg to `nargs='+'` to accept multiple IDs
- Add `--playlist <PLAYLIST_ID>` argument
- Add `get_user_playlist_info(playlist_id)` method querying `/api/v2/collections/` (adapted for v2 API + cookie auth)
- Add `check_and_extract_book_id_from_ourn(ourn)` static method
- In main block: if `--playlist`, fetch playlist and extract book IDs; merge with positional IDs; loop `SafariBooks()` per book
- Handle errors per-book without aborting the batch

**Commit 10 — PR #365: Video/MP4 support**
- File: `safaribooks.py`
- Add `is_video_link()` static method (check for `.mp4` suffix)
- Add video link detection in `link_replace()` — route to `Video/` directory
- Add video URL extraction in `parse_html()` — XPath for `//video/source/@src`
- Add `_thread_download_video()` method mirroring image download
- Add `collect_videos()` method
- Create `Video/` directory alongside `Images/`
- Register video items in content.opf manifest with `video/mp4` media-type

### Phase 5: DevOps

**Commit 11 — PR #342: Dockerfile (modernized)**
- New file: `Dockerfile`
- Base: `python:3.11-slim`
- Copy only needed files (`safaribooks.py`, `retrieve_cookies.py`, `requirements.txt`)
- `pip install --no-cache-dir -r requirements.txt`
- Entrypoint: `["python", "safaribooks.py"]`
- Update README with Docker usage showing cookie volume mount:
  ```
  docker run --rm -v $(pwd)/cookies.json:/app/cookies.json -v $(pwd)/Books:/app/Books safaribooks <BOOK_ID>
  ```

---

## Compatibility Notes

- **Phase 1-2** are safe independent fixes with no cross-dependencies
- **Phase 3** (asyncio) must land before Phase 4 features that add new download types (fonts in Phase 3, videos in Phase 4 will use the new async downloader)
- **Phase 4** batch downloads (#89/#354) change the arg parser — all prior phases should be complete first so the single-book flow is stable before adding multi-book
- **Phase 5** Dockerfile is fully independent but should come last so it captures all code changes

## Verification

- **Bug fixes (Phase 1)**: Download a book with CSS assets to verify #165; download a book with `Images/` in chapter paths to verify #308; find a book with non-HTML chapters for #347
- **Phase 2**: Test with `--ssl-skip` behind a proxy; trigger an API error and verify response text appears
- **Phase 3**: Time a download of an image-heavy book before/after asyncio; test font download on a non-English book
- **Phase 4**: Test `safaribooks.py ID1 ID2 ID3`; test `--playlist <id>`; test a book with embedded videos
- **Phase 5**: `docker build . -t safaribooks && docker run --rm -v $(pwd)/cookies.json:/app/cookies.json -v $(pwd)/Books:/app/Books safaribooks <BOOK_ID>`
