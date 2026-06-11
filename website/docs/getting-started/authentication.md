---
sidebar_position: 3
title: Authentication
description: Extract and configure O'Reilly session cookies for safaribooks.
---

# Authentication

safaribooks authenticates with O'Reilly using session cookies from your browser. You need four cookies from a logged-in session.

## Required cookies

| Cookie | Purpose |
|--------|---------|
| `groot_sessionid` | Main session identifier |
| `jwt` | JSON Web Token for API auth |
| `csrf_access_token` | CSRF protection token |
| `logged_in` | Session active flag |

## Extraction methods

### Method 1: Browser export (recommended)

Use the `safari auth extract` command to pull cookies directly from a browser's cookie store.

```bash
safari auth extract --browser chrome
```

Supported browsers: `chrome`, `firefox`, `edge`, `chromium`.

:::tip
Close and reopen your browser before extracting cookies to ensure the cookie store is flushed to disk.
:::

### Method 2: Interactive setup

The guided setup walks you through cookie extraction step by step:

```bash
safari auth setup
```

### Method 3: HTTP header import

Copy the `Cookie` header from a request in your browser's DevTools (Network tab) and pass it directly:

```bash
safari auth import --header "groot_sessionid=abc123; jwt=eyJ...; csrf_access_token=xyz; logged_in=y"
```

### Method 4: File import

Export cookies to a JSON file and import them:

```json title="cookies.json"
{
  "groot_sessionid": "abc123",
  "jwt": "eyJhbGciOiJSUzI1NiIs...",
  "csrf_access_token": "xyz789",
  "logged_in": "y"
}
```

```bash
safari auth import --file cookies.json
```

### Method 5: JavaScript console

Run this snippet in your browser console on an O'Reilly page, then import the output:

```javascript
JSON.stringify(
  Object.fromEntries(
    document.cookie.split('; ').map(c => c.split('='))
  )
)
```

Copy the output to a file and use `safari auth import --file`.

## Cookie storage

Cookies are stored at `~/.config/safaribooks/cookies.json` with `0600` permissions (readable only by your user).

## Validating cookies

Check that your stored cookies are valid:

```bash
safari auth validate
```

Check current auth status:

```bash
safari auth status
```

:::warning
O'Reilly session cookies expire after approximately 2 hours. If a download fails mid-way due to expired cookies, see the [session resilience guide](../guides/session-resilience.md).
:::

## Next step

[Download your first book](./first-download.md).
