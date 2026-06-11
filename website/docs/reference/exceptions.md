---
sidebar_position: 4
title: Exceptions
description: Exception hierarchy and when each error is raised.
---

# Exceptions

safaribooks defines a structured exception hierarchy rooted at `SafariBooksError`. All exceptions are defined in `src/safaribooks/core/exceptions.py`.

## Hierarchy

```
SafariBooksError
├── AuthenticationError
├── CookieError
├── ApiError
├── ParsingError
├── DownloadError
└── SearchError
```

## Exception details

### SafariBooksError

Base exception for all safaribooks errors. Catch this to handle any error from the library.

### AuthenticationError

Raised when authentication fails.

**Common causes:**
- Expired session cookies (401/403 from API)
- Invalid or corrupted JWT token
- Session revoked server-side

**Resolution:** Re-extract cookies with `safari auth extract --browser chrome`.

### CookieError

Raised when cookie validation fails.

**Common causes:**
- Missing required cookies (`groot_sessionid`, `jwt`, `csrf_access_token`, `logged_in`)
- Cookie file not found at `~/.config/safaribooks/cookies.json`
- Cookie file has incorrect permissions

**Resolution:** Run `safari auth setup` or `safari auth import` to provide valid cookies.

### ApiError

Raised when an API request fails after all retry attempts are exhausted.

**Common causes:**
- O'Reilly API is down or returning errors
- Invalid book ID or URL
- Network connectivity issues
- Rate limiting (429) that persists beyond retry budget

**Resolution:** Check your network connection and try again. If the error persists, the API may be experiencing issues.

### ParsingError

Raised when HTML/XML parsing fails.

**Common causes:**
- Malformed HTML in chapter content
- Unexpected page structure from API changes
- lxml processing errors

**Resolution:** Try the download again. If it persists, the book may have unusual formatting that the parser can't handle.

### DownloadError

Raised when an asset download (images, CSS, fonts, videos) fails after all retry attempts.

**Common causes:**
- Asset URL returns 404
- CDN issues for image/font hosting
- Network timeout during large image downloads

**Resolution:** Re-run the download. Missing assets are logged but may not prevent EPUB creation.

### SearchError

Raised when a title search fails.

**Common causes:**
- Empty search query
- API search endpoint returns an error
- No results found for the query

**Resolution:** Try a different search term or use the book ID directly.

## Catching errors programmatically

If using safaribooks as a library:

```python
from safaribooks.core.exceptions import (
    SafariBooksError,
    AuthenticationError,
    CookieError,
)

try:
    await downloader.run()
except AuthenticationError:
    print("Session expired, re-extract cookies")
except CookieError:
    print("Missing or invalid cookies")
except SafariBooksError as e:
    print(f"Download failed: {e}")
```
