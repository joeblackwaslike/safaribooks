---
sidebar_position: 3
title: Common Errors
description: Solutions for frequently encountered errors.
---

# Common Errors

Quick reference for the most frequent error messages and their solutions.

## CookieError: Missing required cookies

**Message:** `Missing required cookies: groot_sessionid, jwt`

**Cause:** Cookie file doesn't exist or is missing required cookies.

**Fix:**
```bash
safari auth setup
# or
safari auth extract --browser chrome
```

## AuthenticationError: Session expired

**Message:** `Authentication failed (401)`

**Cause:** Session cookies have expired (typically after ~2 hours).

**Fix:**
```bash
safari auth extract --browser chrome
safari auth validate
```

See [Cookie Expiry](./cookie-expiry.md) for details.

## ApiError: Book not found

**Message:** `API error: 404 for book 1234567890`

**Cause:** Invalid book ID or the book was removed from O'Reilly.

**Fix:**
- Verify the book ID from the O'Reilly URL
- Check that the book is still available on learning.oreilly.com
- Try using the full URL instead of just the ID

## ApiError: Rate limited (429)

**Message:** `API error: 429 Too Many Requests`

**Cause:** Sending requests too quickly. The retry logic handles occasional 429s, but sustained throttling exhausts retries.

**Fix:**
```bash
safari fetch --rate-limit 0.5 9781492056348
```

## ParsingError: Failed to parse chapter

**Message:** `Failed to parse chapter content`

**Cause:** Unusual HTML structure in the chapter that the parser can't handle.

**Fix:** Re-run the download. If it persists, the book may have non-standard formatting. File an issue on GitHub with the book ID.

## DownloadError: Asset download failed

**Message:** `Failed to download image after 3 attempts`

**Cause:** Image or CSS file URL returned errors. This can be a CDN issue or the asset may have been removed.

**Fix:** Re-run the download. Missing assets are logged but the EPUB is still created. The affected images will be blank.

## FileNotFoundError: cookies.json

**Message:** `FileNotFoundError: ~/.config/safaribooks/cookies.json`

**Cause:** No cookies have been set up yet.

**Fix:**
```bash
safari auth setup
```

## ConnectionError: Network unreachable

**Message:** `ConnectionError` or `ConnectTimeout`

**Cause:** No internet connection or O'Reilly servers are unreachable.

**Fix:**
- Check your internet connection
- Try accessing learning.oreilly.com in your browser
- If behind a VPN/proxy, check that it's connected
- Try with `--ssl-skip` if SSL inspection might be the issue
