---
sidebar_position: 3
title: Playlist Download
description: Download all books from an O'Reilly playlist.
---

# Download a Playlist

Download all books in an O'Reilly playlist with a single command.

## Step 1: Find the playlist UUID

Navigate to your playlist on O'Reilly. The UUID is in the URL:

```
https://learning.oreilly.com/playlists/d4f2c4a8-1234-5678-9abc-def012345678/
```

## Step 2: Download

```bash
safari fetch --playlist d4f2c4a8-1234-5678-9abc-def012345678
```

## Step 3: Check the output

All books are saved to the output directory (default: `Books/`):

```
Books/
├── Book One Title.epub
├── Book Two Title.epub
└── Book Three Title.epub
```

## With additional options

```bash
safari fetch \
  --playlist d4f2c4a8-1234-5678-9abc-def012345678 \
  --output ~/oreilly-playlist/ \
  --kindle \
  --rate-limit 0.5
```
