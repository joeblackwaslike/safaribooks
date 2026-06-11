---
sidebar_position: 2
title: API Migration
description: Migration from O'Reilly API v1 to v2.
---

# API Migration (v1 to v2)

safaribooks originally used O'Reilly's v1 API, which was decommissioned. The project has been migrated to the v2 API.

## Background

The original safaribooks (and many forks) used the v1 API at `https://learning.oreilly.com/api/v1/`. When O'Reilly shut down v1, all existing tools broke.

## What changed

| Aspect | v1 API | v2 API |
|--------|--------|--------|
| Base URL | `/api/v1/` | `/api/v2/` |
| Book info | `/api/v1/book/{id}/` | `/api/v2/epubs/urn:orm:book:{id}/` |
| Chapters | `/api/v1/book/{id}/chapter/` | Embedded in book info response |
| Flat chapters | Single endpoint, flat list | Nested TOC structure, recursive parsing |
| Search | `/api/v1/search/` | `/api/v2/search/` |
| Authentication | Same cookie-based | Same cookie-based |

## Adapter layer

The `ApiClient` abstracts the v2 API details behind clean methods:

- `get_book_info(book_id)` -- returns a `BookInfo` model
- `get_chapters(book_id)` -- returns a list of `Chapter` models
- `search(query)` -- returns a `SearchResponse` model

Calling code never sees raw API responses or URL construction.

## Community contribution

This migration was a synthesis of multiple community PRs and forks that attempted the v1-to-v2 migration. The final implementation cherry-picked the best approaches and added:

- Proper v2 response parsing with Pydantic models
- Recursive TOC handling (v2 uses nested structures)
- Updated search endpoint integration
- Comprehensive error handling for v2 error formats

See the [CHANGELOG](https://github.com/joeblackwaslike/safaribooks/blob/master/CHANGELOG.md) for the full migration history.
