# StayPresent — Changelog

## 1.5.12

### Improved

* **The built-in Markdown renderer now renders GitHub-Flavored-Markdown task lists.** `- [ ] todo` / `- [x] done` previously rendered as literal `[ ]`/`[x]` text; each now renders as a disabled checkbox (`<input type="checkbox" disabled>`, checked for `[x]`/`[X]`) with a `task-list-item` class on its `<li>`, matching GitHub's own rendering (including no bullet marker on task items) - complete with nested/ordered-list task items and full inline formatting (bold, links, code, etc.) inside the item text. Only fires on an item's own leading `[ ]`/`[x]` (mirroring GFM's own rule that it must be immediately followed by whitespace) - `[ ]` appearing mid-sentence is left as plain text, unaffected.

* A thorough re-audit of the full codebase (`pinger.py`, `runner.py`, `server.py`, `web.py`, `markdown_renderer.py`) turned up no further correctness bugs beyond what 1.5.7-1.5.11 already addressed - signal handling, list nesting/looseness, setext headings, table detection, URL-scheme sanitization, and balanced-paren URLs were all re-verified against a broad set of hand-built and adversarial inputs (mixed nested lists, loose/tight items, dangerous URL schemes including whitespace/case obfuscation attempts, doubly-nested parens, multi-line setext headings, table-after-paragraph, signal chaining with/without a host-installed handler) with no regressions or new failures found.

---

## 1.5.11

### Fixed

* **Fixed documentation links on the PyPI project page.** Replaced relative README links with absolute GitHub URLs, ensuring documentation links render and open correctly on PyPI while remaining fully functional on GitHub.

---

## 1.5.10

### Fixed

* **A crash-triggered bot restart could hang graceful shutdown indefinitely.** The restart backoff used an uninterruptible `time.sleep()`, so a `Ctrl+C`/`SIGTERM` arriving during that window went unnoticed until the full delay elapsed - and because bot-monitor threads are non-daemon, the process wouldn't actually exit until that new, untracked process (spawned *after* shutdown had already terminated everything it knew about) finished running, which for a long-lived bot could mean never. The backoff now uses an interruptible wait that returns immediately once shutdown begins, and the respawn itself is synchronized with shutdown's own process cleanup so a restart can never slip through as an orphaned, never-terminated process.

* **Markdown heading anchors were broken for headings containing a link, image, or emphasis.** A heading like `## [Link Text](url) Heading` produced a slug that fused the link's URL into the anchor id (e.g. `link-texthttpsexamplecom-heading`) instead of anchoring on the heading's rendered text. Slug generation now strips Markdown syntax down to plain text first (links/images reduce to their label/alt text, emphasis markers unwrap) the same way it already did for inline code, so anchors match what GitHub itself would generate.

* **Markdown links/images could point at script-executing or local-file URL schemes.** `[click me](javascript:alert(1))` rendered a working, clickable `javascript:` link with no sanitization at all. `javascript:`/`vbscript:`/`file:` URLs (and `data:` for links specifically, which can smuggle a full HTML document into a click) are now rejected during rendering and fall back to plain text instead of an active link/image; ordinary `http(s)`, relative, and anchor URLs are unaffected, and `data:` images (a common, inert way to embed small icons) are still allowed.

* **Link/image URLs containing a parenthesis were silently truncated.** A destination like the very common Wikipedia-style `https://en.wikipedia.org/wiki/Foo_(bar)` got cut off at `Foo_(bar` mid-word, leaving a stray `)` in the rendered output, because the URL pattern stopped at the very first `)` it saw. The destination pattern now allows one level of balanced parens inside the URL, matching CommonMark's own handling of this case.

* **`staypresent.web`'s one-time "serves the whole directory" warning wasn't thread-safe.** The set tracking which directories had already been warned about was mutated without holding any lock, unlike every other piece of shared state in that module - two threads registering `html()`/`markdown()` for the same new directory at the same moment could both lose the race and each log the warning. It's now guarded by the same lock as everything else in the module.

* **A query string was silently dropped when redirecting a bare `html()`/`markdown()` path to its trailing-slash form.** Requesting `/dashboard?tab=2` before the trailing slash existed redirected to `/dashboard/`, discarding `?tab=2`. The redirect now carries the original query string through.

---

## 1.5.9

### Fixed

* **`staypresent.run()` no longer enters a permanently unusable state after a failed invocation.** The internal "run once" flag was previously claimed before argument validation, causing any failed validation (such as an invalid bot path, port, or thread count) to permanently prevent subsequent valid calls in the same process. The flag is now set only after all validation succeeds and immediately before the server starts, while maintaining the existing thread-safe locking behavior.

* **Fixed Markdown table detection when a table immediately follows a paragraph.** Tables without a separating blank line were previously parsed as plain paragraph text because paragraph parsing continued before recognizing the upcoming table header. Paragraph parsing now correctly terminates when the following lines form a valid table, allowing the table to render as an independent block.

* **Graceful shutdown via `Ctrl+C` or `SIGTERM` no longer produces an uncaught traceback.** Python's default `SIGINT` handler raises `KeyboardInterrupt`, which bypassed the previous exception handling logic and caused an unnecessary traceback during normal shutdown. The default handler is now treated as the absence of a custom handler, while custom chained handlers are safely wrapped to preserve clean application termination.

* **Fixed parsing of multi-line Setext headings.** Multi-line headings followed by `===` or `---` were not recognized due to incomplete detection logic and an off-by-one boundary check. Setext heading detection now operates during paragraph collection, correctly rendering both H1 and H2 headings without leaking underline characters or unintended horizontal rules into the output.

* **Ordered lists now preserve their starting number.** Lists beginning with values other than `1` now emit the appropriate HTML `start` attribute instead of being implicitly renumbered by browsers.

* **Loose Markdown lists now render correctly.** Blank-line detection previously occurred after list items had already been trimmed, causing every list to render as a tight list. Loose-list detection is now performed before trimming and is consistently applied across the entire list, matching GitHub Flavored Markdown behavior.

* **Fixed nested lists containing different marker types.** Switching between unordered and ordered list markers within nested lists no longer causes the outer list to split into multiple independent lists. Nested lists of either type are now preserved correctly.

* **Removed unnecessary paragraph wrappers from tight list items containing nested sub-lists.** Tight list items now render their leading text inline, with nested lists appended as block content, matching GitHub's rendering behavior.

### Documentation

* **Simplified and reorganized `README.md`.** The README now serves as a concise project overview, focusing on installation, features, quick start, and a high-level API summary, while linking to `DOCUMENTATION.md` for comprehensive reference material. This removes significant duplication without sacrificing documentation coverage.

* **Updated `DOCUMENTATION.md`** to reflect the revised `run()` initialization sequence and the improved Markdown table parsing behavior introduced in this release.


---

## 1.5.8

### Fixed

* **Resolved placeholder restoration for nested inline elements inside Markdown links.** Placeholder tokens created for code spans, escapes, and images embedded within link text were previously restored in forward order, causing nested placeholders to remain unresolved. Restoration now occurs in reverse order, ensuring nested placeholders are correctly expanded before the final link is rendered.

* **Fixed Markdown formatting within link text.** Emphasis, bold, and strikethrough syntax inside link labels is now processed correctly before the anchor element is generated, allowing formatted link text to render as expected.

* **`active_cron_handles()` now reliably tracks fire-and-forget cron jobs.** Cron handles were previously stored in a `WeakSet`, allowing them to be garbage-collected immediately if callers did not retain a reference. Handles are now stored using strong references, removed when explicitly stopped, and automatically pruned once their associated threads exit.

* **Removed unreachable code from `pinger.py`.** The `_ANY_HOSTS` collection included an empty-string alias that could never be reached because `_build_url()` already rejected empty or whitespace-only host values during validation.

* **`staypresent.web.json()` now validates payloads eagerly.** JSON serialization is performed when `json()` is called rather than waiting for the first request, allowing invalid payloads to fail immediately with a `TypeError` instead of producing a runtime HTTP 500 response.

* **`staypresent.web.markdown(favicon=...)` now validates local favicon paths at registration time.** Local favicon files are checked for existence when the route is registered, providing immediate feedback through `FileNotFoundError` instead of deferring failures until the browser requests the asset.

* **`staypresent.run()` now preserves existing signal handlers.** Previously installed `SIGINT` and `SIGTERM` handlers are now chained rather than replaced, allowing host applications to retain their own shutdown behavior. A new `install_signal_handlers=False` option has also been introduced for applications that prefer to manage signal handling themselves.

* **Calling `staypresent.run()` multiple times now produces a clear error message.** Instead of failing later with a generic socket binding error, subsequent invocations now raise a descriptive `RuntimeError` explaining that only a single `run()` call is supported per process and recommending multi-bot configuration when appropriate.

### Documentation

* **Expanded security guidance for `staypresent.web.html()` and `staypresent.web.markdown()`.** Documentation now explicitly explains that registering a local file exposes all files within the same directory as static assets, not just those referenced by the page. The potential security implications are highlighted in the documentation, and the framework now emits a one-time warning whenever a directory is exposed in this manner.

* **Updated documentation** to cover the new `install_signal_handlers` parameter, eager validation performed by `staypresent.web.json()` and `staypresent.web.markdown(favicon=...)`, and the new fail-fast behavior when `staypresent.run()` is invoked more than once.

---

## 1.5.7

### Fixed

* **Resolved double-escaping of Markdown link and image URLs.** URL, title, and alt-text attributes were previously HTML-escaped more than once, resulting in malformed links containing escaped entities such as `&amp;amp;`. Attribute generation now escapes only quotation marks, preserving the existing HTML escaping performed earlier in the rendering pipeline.

* **Fixed truncated Markdown autolinks containing query parameters.** Autolinks were previously terminated at the first `&` character, causing URLs with query strings to render incorrectly. The parser now correctly captures the complete URL before generating the final link.

* **Improved path normalization in `staypresent.web`.** Leading and trailing whitespace is now removed before route normalization, preventing accidental registration of unreachable routes caused by stray spaces.

* **Removed unused `_BUILTIN_DEFAULT_PATHS` implementation.** Built-in default routes are now referenced through the new `web.is_builtin_default_path()` helper, ensuring a single authoritative definition and simplifying future maintenance.

### Improved

* **Added runtime introspection for cron pingers.** Introduced a lightweight registry, the new `staypresent.active_cron_handles()` API, and the `CronHandle.url` property. During shutdown, `run()` now reports any active cron pingers for visibility without altering their lifecycle or shutdown behavior.

* **Warn when `threads=` has no effect.** A warning is now emitted whenever a non-default thread count is supplied in configurations where the setting cannot be applied, such as development mode or when Waitress is unavailable. This makes ignored configuration values explicit instead of silently accepting them.

### Documentation

* Clarified that route normalization removes surrounding whitespace.

* Documented that Markdown link, image, and autolink escaping is applied exactly once, including examples involving query-string URLs.

* Added documentation for the new `staypresent.active_cron_handles()` API and the `CronHandle.url` property.

* Documented the conditions under which the `threads=` parameter is ignored and the corresponding runtime warning.

* Confirmed that the renderer's intentionally limited CommonMark feature set (including the absence of footnotes, definition lists, and mathematical notation) remains unchanged, and reiterated that upfront validation of `bot_module` is an intentional design decision.

---

## 1.5.6 and Earlier

Earlier release history remains available in the project's Git history.