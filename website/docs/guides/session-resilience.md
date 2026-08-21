---
sidebar_position: 7
title: Session Resilience
description: Handle cookie expiry during long downloads.
---

# Session Resilience

O'Reilly session cookies expire after approximately 2 hours. For large books or batch downloads, your session may expire mid-download.

## What happens on expiry

When cookies expire during a download:

1. The API returns a 401/403 response
2. safaribooks detects the authentication failure
3. The current cookie file is backed up as `cookies.json.expired`
4. The download pauses with an `AuthenticationError`

## Re-extraction flow

To resume after expiry:

```bash
# Step 1: Re-extract fresh cookies
safari auth extract --browser chrome

# Step 2: Verify the new cookies work
safari auth validate

# Step 3: Re-run the download
safari fetch 9781492056348
```

:::info
safaribooks downloads chapters and assets as it goes, so restarting will re-download from the beginning. There is no resume-from-checkpoint support yet.
:::

## Reducing the risk

For long downloads, reduce request rate to extend the useful window of your session:

```bash
safari fetch --rate-limit 0.5 --file big-book-list.txt
```

## Cookie backup

When cookies expire, the previous file is preserved:

```
~/.config/safaribooks/cookies.json           # current (freshly extracted)
~/.config/safaribooks/cookies.json.expired    # previous (expired)
```

This lets you inspect the expired cookies if needed for debugging.

## Tips

- Extract cookies right before starting a large batch
- Use `safari auth status` to check remaining session validity before starting
- Consider splitting very large book lists into smaller batches
