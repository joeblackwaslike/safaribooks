---
sidebar_position: 3
title: Models
description: Pydantic v2 data models used throughout safaribooks.
---

# Models

safaribooks uses Pydantic v2 models for type-safe data handling throughout the pipeline. All models are defined in `src/safaribooks/core/models.py`.

## Book metadata

### Author

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Author's full name |

### Publisher

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Publisher name |

### Subject

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Subject/category name |

### BookInfo

The primary book metadata model, populated from the v2 API response.

| Field | Type | Description |
|-------|------|-------------|
| `title` | `str` | Book title |
| `identifier` | `str` | O'Reilly identifier |
| `isbn` | `str` | ISBN |
| `description` | `str` | Book description/blurb |
| `web_url` | `str` | URL on learning.oreilly.com |
| `rights` | `str` | Copyright/license text |
| `cover` | `str` | Cover image URL |
| `authors` | `list[Author]` | List of authors |
| `publishers` | `list[Publisher]` | List of publishers |
| `subjects` | `list[Subject]` | Subject categories |
| `issued` | `str` | Publication date |

### Stylesheet

| Field | Type | Description |
|-------|------|-------------|
| `url` | `str` | CSS stylesheet URL |

## Chapter content

### Chapter

Represents a single chapter in the book.

| Field | Type | Description |
|-------|------|-------------|
| `filename` | `str` | Output filename (e.g., `chapter001.xhtml`) |
| `title` | `str` | Chapter title |
| `content_url` | `str` | API URL for chapter HTML content |
| `asset_base_url` | `str` | Base URL for resolving relative asset paths |
| `images` | `list[str]` | Discovered image URLs |
| `stylesheets` | `list[Stylesheet]` | Referenced stylesheets |
| `site_styles` | `list[str]` | Inline site CSS URLs |

### TocEntry

Recursive model for the table of contents tree.

| Field | Type | Description |
|-------|------|-------------|
| `depth` | `int` | Nesting depth level |
| `fragment` | `str` | Fragment identifier |
| `id` | `str` | Entry ID |
| `label` | `str` | Display label |
| `href` | `str` | Link target |
| `children` | `list[TocEntry]` | Nested child entries |

:::info
`TocEntry` is self-referencing -- its `children` field contains more `TocEntry` objects, forming an arbitrarily deep tree.
:::

## Authentication

### CookieSet

Validated cookie container with enforcement of required cookies.

| Field | Type | Description |
|-------|------|-------------|
| `cookies` | `dict[str, str]` | Cookie name-value pairs |

Required cookies validated on construction:
- `groot_sessionid`
- `jwt`
- `csrf_access_token`
- `logged_in`

A `CookieError` is raised if any required cookie is missing.

## Search

### SearchResult

A single search result from the O'Reilly API.

| Field | Type | Description |
|-------|------|-------------|
| `isbn` | `str` | ISBN |
| `identifier` | `str` | O'Reilly identifier |
| `archive_id` | `str` | Archive identifier |
| `title` | `str` | Book title |
| `authors` | `list[str]` | Author names |
| `publishers` | `str` | Publisher name |
| `cover_url` | `str` | Cover image URL |
| `web_url` | `str` | URL on learning.oreilly.com |
| `issued` | `str` | Publication date |
| `description` | `str` | Description/blurb |

**Computed property:** `book_id` -- returns the identifier suitable for passing to `safari fetch`.

### SearchResponse

Paginated search response.

| Field | Type | Description |
|-------|------|-------------|
| `results` | `list[SearchResult]` | Search results |
| `count` | `int` | Results in this page |
| `total` | `int` | Total matching results |
| `next` | `str \| None` | URL of next page |
| `previous` | `str \| None` | URL of previous page |

## HTML parsing

### ParseResult

Output of the HTML parser after processing a chapter.

| Field | Type | Description |
|-------|------|-------------|
| `page_css` | `str` | Extracted page-level CSS |
| `body_xhtml` | `str` | Cleaned XHTML body content |
| `discovered_css` | `list[str]` | CSS URLs found in the HTML |
| `discovered_images` | `list[str]` | Image URLs found in the HTML |
| `discovered_videos` | `list[str]` | Video URLs found in the HTML |
| `cover_src` | `str \| None` | Cover image source if detected |
