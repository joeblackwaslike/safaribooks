# Plan: Unified Cookie Auth System for safaribooks

## Context

O'Reilly blocked programmatic login, so the tool depends entirely on browser-extracted cookies. Our fork (branch `feat/migrate-api-v2`) already has the v2 API migration and a basic `retrieve_cookies.py` with paste and browser-auto modes. But the current cookie workflow has significant gaps: only two input formats, no validation, destructive behavior on expiry (deletes `cookies.json`), no mid-download recovery, and sparse docs.

Six upstream PRs were analyzed. The best ideas come from:
- **PR #373** — clear cookie extraction documentation and headless environment instructions
- **PR #256** — EditThisCookie extension JSON parser (array-of-objects format)
- **PR #32** — raw `Cookie:` header string parser from Network panel
- **PR #350** — not the code (endpoint is dead), but the community suggestion to use `browser_cookie3` (already implemented) and the lesson that mobile API tokens are fragile

PRs #351 and #350's code are obsolete and should be skipped entirely.

## Approach

Consolidate all useful cookie handling ideas into a single, robust `retrieve_cookies.py` with multi-format input, validation, and better UX. Improve `safaribooks.py` to validate cookies upfront and handle mid-session expiry gracefully. Rewrite the README auth section.

---

## Phase 1: Cookie Input Format Consolidation

**File: `retrieve_cookies.py`**

Absorb the parsing logic from PRs #256 and #32 into the existing file. No new scripts.

1. **Add `from_header(raw)` function** — parses raw `Cookie: k1=v1; k2=v2` header strings (PR #32 idea). Split on `; `, split each on first `=`, handle `Cookie: ` prefix if present.

2. **Add `from_file(filepath)` function** — reads a file and auto-detects format:
   - JSON dict → use directly (our flat format)
   - JSON array of `{name, value, domain}` objects → convert (PR #256 EditThisCookie format), filter to `.oreilly.com`
   - Not valid JSON → try parsing as raw cookie header string

3. **Enhance `from_paste()` to auto-detect** — instead of requiring flat JSON only, try all three formats: flat JSON dict, extension array, raw header string. This means users can paste whatever they have and it just works.

4. **Add `_normalize_cookies(cookies)` helper** — strips whitespace, removes empty-value entries.

5. **New CLI flags:**
   - `--file / -f PATH` — import from file (any format)
   - `--header / -H STRING` — parse raw cookie header
   - `--validate / -v` — check existing `cookies.json` without overwriting
   - `--output / -o PATH` — custom output path

## Phase 2: Cookie Validation

**Files: `retrieve_cookies.py` + `safaribooks.py`**

1. **Add `validate_cookies(cookies_dict)` in `retrieve_cookies.py`** — returns `(is_valid, warnings)`. Checks:
   - At least 3 cookies present
   - At least one cookie name containing "session", "jwt", "token", "logged", or "csrf" (heuristic, resilient to name changes)
   - No empty-value cookies
   
2. **Run validation after every extraction** in `retrieve_cookies.py` — give immediate feedback before saving.

3. **Add `--validate` flag** — loads existing `cookies.json`, runs validation, optionally hits profile URL to confirm session is live.

4. **Pre-flight validation in `SafariBooks.__init__()`** (safaribooks.py ~line 336) — after loading cookies, run `validate_cookies()` and warn/exit before attempting download.

5. **Fix `api_error()` destructive behavior** (safaribooks.py lines 211-212) — rename `cookies.json` to `cookies.json.expired` instead of deleting it. Improve error message to point users to `retrieve_cookies.py`.

## Phase 3: Session Resilience

**File: `safaribooks.py`**

1. **Add `_try_cookie_refresh()` method** — reloads `cookies.json` from disk (in case user re-extracted in another terminal). Returns `True` if cookies were refreshed, `False` otherwise. Includes a retry counter to prevent infinite loops.

2. **Add retry logic in `requests_provider()`** (~line 425) — when a request returns 401/403 or redirects to `/login`, call `_try_cookie_refresh()` and retry once. If that fails, prompt user interactively: "Session expired. Re-extract cookies in another terminal, then press Enter to continue."

3. **This preserves download progress** — chapters already cached on disk aren't re-downloaded. Critical for large books.

## Phase 4: Security Hardening

**Files: both**

1. **Set file permissions** — `os.chmod(COOKIES_FILE, 0o600)` after writing `cookies.json` (wrapped in try/except for Windows).

2. **Scrub cookies from logs** — in `Display.save_last_request` (~line 134), mask `Cookie:` and `Set-Cookie:` header values with `[REDACTED]`.

## Phase 5: Documentation

**File: `README.md`**

Rewrite the "Getting Cookies" section with five clearly numbered methods:
1. **Paste mode** (recommended) — JS console snippet → paste into `retrieve_cookies.py`
2. **Raw cookie header** — copy from Network panel → `--header` flag
3. **Browser extension export** — EditThisCookie → `--file` flag
4. **Auto-extract from browser** — `browser_cookie3` → `-b chrome`
5. **Manual `cookies.json`** — for advanced users, show format

Add troubleshooting section (Out-of-Session, no cookies found, browser lock files) and expanded security notes.

---

## Files to Modify

| File | Changes |
|------|---------|
| `retrieve_cookies.py` | Add `from_header()`, `from_file()`, `validate_cookies()`, `_normalize_cookies()`, enhance `from_paste()`, new CLI flags |
| `safaribooks.py` | Pre-flight validation, fix `api_error()` backup-not-delete, add `_try_cookie_refresh()`, retry logic in `requests_provider()`, cookie scrubbing in logs |
| `README.md` | Rewrite auth/cookie section with all methods, troubleshooting, security notes |

## Existing Code to Reuse

- `from_browser()` in `retrieve_cookies.py` — works as-is, no changes needed
- `handle_cookie_update()` in `safaribooks.py:418-423` — already handles Set-Cookie refresh during active session
- `COOKIES_FILE` constant in `safaribooks.py:22` — shared between both files via import
- `check_login()` in `safaribooks.py` — already validates session via HTTP, reuse for `--validate` active check

## Verification

1. Extract cookies via each method (paste flat JSON, paste header, paste extension array, `--file`, `-b chrome`) — all produce valid `cookies.json`
2. Run `--validate` on fresh cookies — reports valid
3. Run with valid cookies — authenticates and downloads
4. Corrupt `cookies.json` (empty dict) — clear validation error, not crash
5. Let cookies expire mid-download — should prompt for re-extraction, not delete file
6. Check `cookies.json` has 0600 permissions on Unix
7. Check log files don't contain raw cookie values
8. Run `retrieve_cookies.py --help` — shows all new flags with examples

## Implementation Priority

Phases 1-2 are the highest impact (multi-format input + validation). Phase 3 (session resilience) is the biggest UX win for long downloads. Phases 4-5 are polish. Each phase is independently shippable.
