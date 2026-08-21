---
sidebar_position: 1
title: Cookie Expiry
description: Diagnose and fix expired session cookies.
---

# Cookie Expiry

O'Reilly session cookies expire after approximately 2 hours. This is the most common cause of download failures.

## Symptoms

- Download fails with `AuthenticationError`
- API returns 401 or 403 status codes
- Error message mentions "authentication" or "session expired"
- Download succeeds for the first few chapters then fails

## Diagnosis

Check your current auth status:

```bash
safari auth status
```

If cookies are expired, you'll see an error indicating the session is no longer valid.

## Fix

Re-extract fresh cookies:

```bash
# Step 1: Extract new cookies
safari auth extract --browser chrome

# Step 2: Verify they work
safari auth validate

# Step 3: Re-run the download
safari fetch 9781492056348
```

## What happens to old cookies

When cookies expire during a download, safaribooks backs up the expired file:

```
~/.config/safaribooks/cookies.json            # replaced with new cookies
~/.config/safaribooks/cookies.json.expired     # backup of expired cookies
```

## Prevention

- Extract cookies immediately before starting large batch downloads
- Use a lower `--rate-limit` (e.g., `0.5`) to reduce download time
- Split large book lists into smaller batches

:::tip
If you're downloading many books, consider running `safari auth status` between batches to check if your session is still valid.
:::
