---
sidebar_position: 1
title: Overview
description: What safaribooks is, who it's for, and where to start.
---

# Getting Started

**safaribooks** is an async Python CLI that downloads books from O'Reilly's online library as EPUB files you can read offline in any e-reader.

## What it does

- Downloads complete books including chapters, images, CSS, fonts, and videos
- Produces standards-compliant EPUB files readable by any EPUB-compatible reader
- Supports bulk downloads via playlists, file lists, or multiple book IDs
- Handles authentication, rate limiting, and retries automatically

## Who it's for

You need an active O'Reilly (formerly Safari Books Online) subscription. safaribooks uses your session cookies to authenticate API requests.

## Where to start

1. **[Install safaribooks](./installation.md)** -- get the CLI on your machine
2. **[Set up authentication](./authentication.md)** -- extract and configure your O'Reilly session cookies
3. **[Download your first book](./first-download.md)** -- fetch a book and open the EPUB

## Requirements

- Python 3.12 or later
- An active O'Reilly subscription
- Session cookies from a logged-in browser session
