# Contributors & Credits

This fork builds on the incredible work of the open-source community. The O'Reilly v1 API died quietly, and the upstream repo (`lorenzodifuccia/safaribooks`) hasn't merged fixes in years. Rather than let the tool die, we evaluated every open PR, cherry-picked the best ideas, and synthesized them into a working v2 migration.

**Every contributor listed here made this fork possible.** Their PRs provided the research, code patterns, bug discoveries, and feature ideas that informed our implementation — even when we couldn't merge their code directly (due to conflicts, v1 assumptions, or architectural differences).

> **Want your contribution removed?** We take this seriously. If you'd like your work retracted from this fork, contact **[me@joeblack.nyc](mailto:me@joeblack.nyc)** and we'll remove it promptly. No questions asked.

---

## Core Contributors

These PRs directly shaped the v2 API migration — the foundation of this fork.

<table>
<tr>
<td align="center" width="150">
<a href="https://github.com/wraymo">
<img src="https://avatars.githubusercontent.com/u/37269683?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>wraymo</b>
</a>
</td>
<td>

**[PR #379 — Migrate from dead v1 API to v2 API](https://github.com/lorenzodifuccia/safaribooks/pull/379)**

The backbone of our migration. Cleanest diff of all v2 PRs, with iterative chapter pagination (fixing `RecursionError` on 700+ chapter books), `normalize_toc()` for v2→v1 TOC conversion, and tested end-to-end on 9 real books. This PR provided the foundation architecture: transform v2 responses into v1 shapes at the API boundary so downstream code needs zero changes.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/sohailnajar">
<img src="https://avatars.githubusercontent.com/u/5450507?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Sohail Najar</b><br>
<sub>@sohailnajar</sub>
</a>
</td>
<td>

**[PR #377 — Migrate to O'Reilly API v2 and fix cookie-based authentication](https://github.com/lorenzodifuccia/safaribooks/pull/377)**

Contributed critical metadata enrichment via the search API (authors, publishers, subjects), the `unquote()` fix for URL-encoded filenames, redirect-following on login check, and the two-mode `retrieve_cookies.py` rewrite (paste + browser auto-extract). Our cookie auth system is built on this foundation.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/frozenprocess">
<img src="https://avatars.githubusercontent.com/u/54559947?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Reza</b><br>
<sub>@frozenprocess</sub>
</a>
</td>
<td>

**[PR #370 — Support for API v2](https://github.com/lorenzodifuccia/safaribooks/pull/370)**

Provided the `parse_json_response()` error handling pattern with detailed diagnostics for non-JSON responses, bad status codes, and parse failures. This helper became central to our API layer's resilience.

</td>
</tr>
</table>

---

## Image & EPUB Quality Contributors

These PRs fixed cover images, Apple Books compatibility, and EPUB output quality.

<table>
<tr>
<td align="center" width="150">
<a href="https://github.com/stevenl">
<img src="https://avatars.githubusercontent.com/u/1205849?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Steven Lee</b><br>
<sub>@stevenl</sub>
</a>
</td>
<td>

**[PR #332 — Make cover art show in Apple Books library](https://github.com/lorenzodifuccia/safaribooks/pull/332)**

Essential 6-line fix: the OPF `<meta name="cover">` tag must reference a manifest item ID, not a filename. Without this, Apple Books can't display cover art in the library grid view.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/realrisman">
<img src="https://avatars.githubusercontent.com/u/9587306?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Muhamad Risman</b><br>
<sub>@realrisman</sub>
</a>
</td>
<td>

**[PR #364 — Improve cover image quality and fix duplicate cover page issue](https://github.com/lorenzodifuccia/safaribooks/pull/364)**

Two fixes in one: HD cover URL fallback chain (tries `/orig/` before `/thumb/`) for higher-resolution covers, and duplicate cover prevention (checks if a cover chapter already exists before prepending a default one).

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/tuanchauict">
<img src="https://avatars.githubusercontent.com/u/955306?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Tuan Chau</b><br>
<sub>@tuanchauict</sub>
</a>
</td>
<td>

**[PR #120 — Support resize image and change image quality](https://github.com/lorenzodifuccia/safaribooks/pull/120)**

Added Pillow-based image resize/compression via `--image-max-size` and `--image-quality` CLI flags. Useful for reducing EPUB file size on image-heavy technical books.

</td>
</tr>
</table>

---

## Cookie & Authentication Contributors

These PRs contributed ideas and code patterns for the cookie extraction and authentication system.

<table>
<tr>
<td align="center" width="150">
<a href="https://github.com/AntonBronnfjell">
<img src="https://avatars.githubusercontent.com/u/71841746?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Pedro Antonio Escalante Martinez</b><br>
<sub>@AntonBronnfjell</sub>
</a>
</td>
<td>

**[PR #373 — Enhance README with cookie extraction instructions](https://github.com/lorenzodifuccia/safaribooks/pull/373)** and **[PR #372 — Improve error handling](https://github.com/lorenzodifuccia/safaribooks/pull/372)**

PR #373 contributed the browser console JS snippet and Chromium remote debugging instructions for cookie extraction. PR #372's `--ssl-skip` flag concept was adopted for corporate proxy environments.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/juanmougan">
<img src="https://avatars.githubusercontent.com/u/5788211?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Juan Manuel Mougan</b><br>
<sub>@juanmougan</sub>
</a>
</td>
<td>

**[PR #256 — Parsing cookies from an extension](https://github.com/lorenzodifuccia/safaribooks/pull/256)**

Contributed the EditThisCookie extension JSON parser (array-of-objects format). This idea was absorbed into our multi-format cookie auto-detection system.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/dafalcon">
<img src="https://avatars.githubusercontent.com/u/224644?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Dan Falcone</b><br>
<sub>@dafalcon</sub>
</a>
</td>
<td>

**[PR #32 — Add a script to import cookies](https://github.com/lorenzodifuccia/safaribooks/pull/32)**

The original cookie import script concept. Its raw `Cookie:` header string parsing approach was adopted for our `--header` flag, letting users paste directly from browser Network panel.

</td>
</tr>
</table>

---

## Bug Fix & Robustness Contributors

These PRs fixed crashes, parsing failures, and edge cases.

<table>
<tr>
<td align="center" width="150">
<a href="https://github.com/spacewander">
<img src="https://avatars.githubusercontent.com/u/4161644?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>罗泽轩</b><br>
<sub>@spacewander</sub>
</a>
</td>
<td>

**[PR #165 — Don't write CSS if download failed](https://github.com/lorenzodifuccia/safaribooks/pull/165)** and **[PR #166 — Print raw response on error](https://github.com/lorenzodifuccia/safaribooks/pull/166)**

Two critical robustness fixes: #165 prevents a crash when CSS download fails (`response == 0` → accessing `.content` on an int). #166's pattern of including truncated `response.text` in error output was adopted for better debugging.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/darren-gibson">
<img src="https://avatars.githubusercontent.com/u/2168022?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Darren Gibson</b><br>
<sub>@darren-gibson</sub>
</a>
</td>
<td>

**[PR #308 — Reduce false positives in link_replace](https://github.com/lorenzodifuccia/safaribooks/pull/308)**

Fixed a bug where HTML page links containing substrings like "cover" or "images" (e.g., `Images/ch08.xhtml#sec-ggg`) were incorrectly routed to the Images directory. The fix only applies image-keyword matching when the link is not an HTML page.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/dreampuf">
<img src="https://avatars.githubusercontent.com/u/353644?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Dreampuf</b><br>
<sub>@dreampuf</sub>
</a>
</td>
<td>

**[PR #347 — Non-HTML root page parsing](https://github.com/lorenzodifuccia/safaribooks/pull/347)**

Some book chapters lack `<html>` root tags, causing lxml parse failures. This PR adds an html5lib fallback parser — a small, targeted fix that's lighter than the alternative BeautifulSoup approach.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/holzkohlengrill">
<img src="https://avatars.githubusercontent.com/u/12732886?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Marcel Schmalzl</b><br>
<sub>@holzkohlengrill</sub>
</a>
</td>
<td>

**[PR #276 — Extract book ID from URL](https://github.com/lorenzodifuccia/safaribooks/pull/276)**

QoL improvement: users often paste full O'Reilly URLs instead of bare book IDs, causing an `OSError` on Windows. This PR extracts the numeric ID from URLs via regex, making the CLI more forgiving.

</td>
</tr>
</table>

---

## Feature Contributors

These PRs proposed new capabilities adopted into the roadmap.

<table>
<tr>
<td align="center" width="150">
<a href="https://github.com/chuxiuhong">
<img src="https://avatars.githubusercontent.com/u/14999649?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>@chuxiuhong</b>
</a>
</td>
<td>

**[PR #343 — Font downloading for non-English books](https://github.com/lorenzodifuccia/safaribooks/pull/343)**

Non-English books reference `.otf` fonts in CSS that weren't being downloaded. This PR adds `collect_fonts()` mirroring the existing CSS/image download pattern — critical for i18n support.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/amit-gp">
<img src="https://avatars.githubusercontent.com/u/9801565?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Amit Gupta</b><br>
<sub>@amit-gp</sub>
</a>
</td>
<td>

**[PR #354 — Download books from playlists](https://github.com/lorenzodifuccia/safaribooks/pull/354)**

Added `--playlist` flag to download all books from an O'Reilly playlist/collection. Filters out non-book content (videos, chapters) and downloads sequentially. Being combined with PR #89's multi-ID concept.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/detvdl">
<img src="https://avatars.githubusercontent.com/u/8858957?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Detlev V.</b><br>
<sub>@detvdl</sub>
</a>
</td>
<td>

**[PR #89 — Allow multiple simultaneous book IDs](https://github.com/lorenzodifuccia/safaribooks/pull/89)**

The concept of accepting multiple positional book IDs was adopted and is being combined with PR #354's playlist logic for a unified batch download system.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/diegorodriguezv">
<img src="https://avatars.githubusercontent.com/u/319701?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>@diegorodriguezv</b>
</a>
</td>
<td>

**[PR #204 — Asyncio parallel downloads](https://github.com/lorenzodifuccia/safaribooks/pull/204)**

Replaces the dead multiprocessing code with asyncio, solving cross-platform issues (SSL context on Windows/macOS). Reported 30min→12min speedup on image-heavy books.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/dsouzaankit">
<img src="https://avatars.githubusercontent.com/u/30167433?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Ankit Dsouza</b><br>
<sub>@dsouzaankit</sub>
</a>
</td>
<td>

**[PR #365 — Video/MP4 support](https://github.com/lorenzodifuccia/safaribooks/pull/365)**

Adds download support for embedded MP4 video clips, extending the image download pattern with a `Video/` directory and proper `video/mp4` manifest entries.

</td>
</tr>
<tr>
<td align="center" width="150">
<a href="https://github.com/ukazap">
<img src="https://avatars.githubusercontent.com/u/6721248?v=4" width="80" height="80" style="border-radius:50%"><br>
<b>Ukaza Perdana</b><br>
<sub>@ukazap</sub>
</a>
</td>
<td>

**[PR #342 — Dockerize](https://github.com/lorenzodifuccia/safaribooks/pull/342)**

Clean, minimal Dockerfile approach. Being modernized for Python 3.11+, cookie-based auth (volume mount for `cookies.json`), and updated examples.

</td>
</tr>
</table>

---

## PRs Reviewed but Not Adopted

These PRs were carefully evaluated but not included — either because they conflicted with our architecture, were superseded by better approaches, or had issues that prevented direct use. We still appreciate the effort and ideas behind each one.

| PR | Author | Title | Why not adopted |
|----|--------|-------|-----------------|
| [#371](https://github.com/lorenzodifuccia/safaribooks/pull/371) | [A Farzat](https://github.com/Farzat07) | Switch to API v2 | Syntax errors prevented direct use |
| [#356](https://github.com/lorenzodifuccia/safaribooks/pull/356) | [Bhatt Umang](https://github.com/bhattumang7) | V2 bug fixes | Orthogonal Kindle/encoding fixes, not a v2 migration |
| [#351](https://github.com/lorenzodifuccia/safaribooks/pull/351) | [Jason Zhu](https://github.com/jasonz-ncc42) | Manual cookie.json setup | Obsolete — covered by our cookie guide |
| [#350](https://github.com/lorenzodifuccia/safaribooks/pull/350) | [@821wkli](https://github.com/821wkli) | Fixed login with --cred | Endpoint is dead; community suggestion for `browser_cookie3` was noted |
| [#325](https://github.com/lorenzodifuccia/safaribooks/pull/325) | [sontek](https://github.com/sontek) | BeautifulSoup for M1 ARM | Heavy dependency; M1 lxml issues resolved in newer versions; PR #347 is lighter |
| [#320](https://github.com/lorenzodifuccia/safaribooks/pull/320) | [@0xHanan](https://github.com/0xHanan) | Fix staticmethod crash | Method doesn't exist in our codebase |
| [#207](https://github.com/lorenzodifuccia/safaribooks/pull/207) | [Anoop Hallur](https://github.com/anooprh) | Download all books in a topic | Breaking arg change; topic downloads too broad; #354 covers batch use cases |
| [#203](https://github.com/lorenzodifuccia/safaribooks/pull/203) | [Avicienna Ulhaq](https://github.com/noxymon) | Higher resolution cover | Massive refactor overlapping with #364; conflicts with v2 migration |
| [#114](https://github.com/lorenzodifuccia/safaribooks/pull/114) | [xyl1null](https://github.com/xyl1null) | Optimisation for Books app | Superseded by #332; contains a Python logic bug |
| [#68](https://github.com/lorenzodifuccia/safaribooks/pull/68) | [Guilherme J. Tramontina](https://github.com/gtramontina) | Dockerize (2019) | Superseded by #342 |
| [#25](https://github.com/lorenzodifuccia/safaribooks/pull/25) | [Eduardo Minguez](https://github.com/e-minguez) | Dockerfile (2018) | Superseded by #342; maintainer declined original |

---

## How This Fork Was Built

This fork was created by [Joe Black](https://github.com/joeblackwaslike) using [Claude Code](https://claude.ai/code) to systematically:

1. **Evaluate** all 30+ upstream PRs for quality, compatibility, and relevance
2. **Plan** the optimal combination of ideas across 5 detailed implementation plans
3. **Implement** the v2 API migration by synthesizing the best approaches from multiple PRs
4. **Review** each change through multiple rounds of code review

The implementation plans are preserved in [`docs/plans/`](plans/) for full transparency on what was adopted, what was skipped, and why.

### Plan Index

| # | Plan | PRs Referenced |
|---|------|---------------|
| 1 | [Cherry-Pick Upstream PR](plans/01-cherry-pick-upstream-pr.md) | General procedure |
| 2 | [Migrate API v1 to v2](plans/02-migrate-api-v1-to-v2.md) | #379, #377, #370, #373 |
| 3 | [Unified Cookie Auth System](plans/03-unified-cookie-auth-system.md) | #373, #256, #32, #350 |
| 4 | [Image Quality & Apple Books Fixes](plans/04-image-quality-apple-books-fixes.md) | #332, #364, #120, #203, #114 |
| 5 | [Upstream PR Evaluation](plans/05-upstream-pr-evaluation.md) | #165, #308, #347, #276, #343, #354, #89, #204, #365, #342, #372, #166, #207, #325, #320, #68, #25 |

---

## All Referenced PRs at a Glance

| PR | Author | Status in Fork | Category |
|----|--------|---------------|----------|
| [#379](https://github.com/lorenzodifuccia/safaribooks/pull/379) | [@wraymo](https://github.com/wraymo) | **Adopted** — core v2 migration | API |
| [#377](https://github.com/lorenzodifuccia/safaribooks/pull/377) | [@sohailnajar](https://github.com/sohailnajar) | **Adopted** — metadata + cookies | API + Auth |
| [#370](https://github.com/lorenzodifuccia/safaribooks/pull/370) | [@frozenprocess](https://github.com/frozenprocess) | **Adopted** — error handling | API |
| [#373](https://github.com/lorenzodifuccia/safaribooks/pull/373) | [@AntonBronnfjell](https://github.com/AntonBronnfjell) | **Adopted** — JS snippet docs | Auth |
| [#372](https://github.com/lorenzodifuccia/safaribooks/pull/372) | [@AntonBronnfjell](https://github.com/AntonBronnfjell) | **Partial** — SSL-skip flag only | Error handling |
| [#332](https://github.com/lorenzodifuccia/safaribooks/pull/332) | [@stevenl](https://github.com/stevenl) | **Adopted** — Apple Books fix | EPUB quality |
| [#364](https://github.com/lorenzodifuccia/safaribooks/pull/364) | [@realrisman](https://github.com/realrisman) | **Adopted** — HD covers | EPUB quality |
| [#120](https://github.com/lorenzodifuccia/safaribooks/pull/120) | [@tuanchauict](https://github.com/tuanchauict) | **Adopted** — image resize | EPUB quality |
| [#256](https://github.com/lorenzodifuccia/safaribooks/pull/256) | [@juanmougan](https://github.com/juanmougan) | **Adopted** — cookie format | Auth |
| [#32](https://github.com/lorenzodifuccia/safaribooks/pull/32) | [@dafalcon](https://github.com/dafalcon) | **Adopted** — header parsing | Auth |
| [#165](https://github.com/lorenzodifuccia/safaribooks/pull/165) | [@spacewander](https://github.com/spacewander) | **Adopted** — CSS crash fix | Bug fix |
| [#166](https://github.com/lorenzodifuccia/safaribooks/pull/166) | [@spacewander](https://github.com/spacewander) | **Partial** — error pattern | Bug fix |
| [#308](https://github.com/lorenzodifuccia/safaribooks/pull/308) | [@darren-gibson](https://github.com/darren-gibson) | **Adopted** — link fix | Bug fix |
| [#347](https://github.com/lorenzodifuccia/safaribooks/pull/347) | [@dreampuf](https://github.com/dreampuf) | **Adopted** — HTML fallback | Bug fix |
| [#276](https://github.com/lorenzodifuccia/safaribooks/pull/276) | [@holzkohlengrill](https://github.com/holzkohlengrill) | **Adopted** — URL extraction | QoL |
| [#343](https://github.com/lorenzodifuccia/safaribooks/pull/343) | [@chuxiuhong](https://github.com/chuxiuhong) | **Adopted** — fonts | Feature |
| [#354](https://github.com/lorenzodifuccia/safaribooks/pull/354) | [@amit-gp](https://github.com/amit-gp) | **Adopted** — playlists | Feature |
| [#89](https://github.com/lorenzodifuccia/safaribooks/pull/89) | [@detvdl](https://github.com/detvdl) | **Adopted** — multi-ID concept | Feature |
| [#204](https://github.com/lorenzodifuccia/safaribooks/pull/204) | [@diegorodriguezv](https://github.com/diegorodriguezv) | **Adopted** — async downloads | Performance |
| [#365](https://github.com/lorenzodifuccia/safaribooks/pull/365) | [@dsouzaankit](https://github.com/dsouzaankit) | **Adopted** — video support | Feature |
| [#342](https://github.com/lorenzodifuccia/safaribooks/pull/342) | [@ukazap](https://github.com/ukazap) | **Adopted** — Docker | DevOps |

---

## Original Project

This fork is based on [lorenzodifuccia/safaribooks](https://github.com/lorenzodifuccia/safaribooks) by [Lorenzo Di Fuccia](https://github.com/lorenzodifuccia). The original project made it possible for thousands of O'Reilly subscribers to read their books offline. Thank you, Lorenzo.

---

*Last updated: June 2026*
