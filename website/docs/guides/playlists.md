---
sidebar_position: 2
title: Playlists
description: Download entire O'Reilly playlists.
---

# Playlist Downloads

O'Reilly lets you organize books into playlists. safaribooks can download all books in a playlist with a single command.

## Finding the playlist UUID

1. Log in to [O'Reilly](https://learning.oreilly.com)
2. Navigate to your playlist
3. The UUID is in the URL:

```
https://learning.oreilly.com/playlists/d4f2c4a8-1234-5678-9abc-def012345678/
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                       This is the playlist UUID
```

## Downloading a playlist

```bash
safari fetch --playlist d4f2c4a8-1234-5678-9abc-def012345678
```

All books in the playlist are downloaded sequentially.

## Combining with other options

Playlist downloads support all the same flags as regular downloads:

```bash
safari fetch --playlist d4f2c4a8-... --output ~/library/ --kindle --rate-limit 0.5
```

## Combining playlists with book IDs

Download a playlist plus additional individual books:

```bash
safari fetch 9781492056348 --playlist d4f2c4a8-...
```

:::info
If a book from the playlist already exists in the output directory, it will be re-downloaded. There is no deduplication.
:::
