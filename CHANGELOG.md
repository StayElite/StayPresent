# Changelog

## 1.5.7

### Fixed

- **Markdown renderer: double-escaped/truncated link and image URLs.**
  `staypresent.web.markdown()`'s built-in renderer HTML-escapes each line
  before its link/image/autolink regexes run, but the code that builds the
  final `href`/`src`/`title` attributes was escaping the already-escaped
  URL/title/alt text a second time. Any URL containing `&`, `<`, or `>`
  (i.e. almost any URL with query parameters) rendered a mangled
  attribute, e.g. `[docs](https://example.com/x?a=1&b=2)` produced
  `href="...&amp;amp;b=2"` instead of `href="...&amp;b=2"`. Link/image text
  itself wasn't affected — this only hit the attribute values. Fixed by
  escaping quote characters only when building these attributes, since the
  `&`/`<`/`>` escaping already happened once upstream.
- **Markdown renderer: autolinks truncated at the first `&`.** A related
  bug in the same area: the autolink regex stopped matching at the first
  literal `&` character, which — because the surrounding text is already
  HTML-escaped — shows up as part of an `&amp;` entity for any `&` in the
  original URL. `<https://example.com/x?a=1&b=2>` would render with a
  truncated `href`. Fixed by matching non-greedily up to the closing
  `&gt;` instead of excluding `&` from the captured run.
- **`staypresent.web`: paths with stray leading/trailing whitespace.**
  `_normalize_path()` didn't strip whitespace, so `" /abc"` normalized to
  `"/ /abc"` and `"/abc "` kept its trailing space — either way producing
  a route that could never actually be reached, with no error to catch
  the mistake. Paths are now stripped before normalization.
- **Dead code: `_BUILTIN_DEFAULT_PATHS` wasn't referenced anywhere.**
  `server.py` hardcoded the literal `"/health"` string instead of using
  the constant meant to describe it. Added `web.is_builtin_default_path()`
  and updated `server.py`'s catch-all route to use it, so future built-in
  defaults only need to be added in one place.

### Improved

- **`cron()` pingers are now introspectable from `run()`'s shutdown
  sequence.** Cron background threads are (and remain) daemon threads not
  tracked by `run()`'s process-management state — this is intentional and
  unchanged. What's new: a lightweight registry plus a new
  `staypresent.active_cron_handles()` function, and a `CronHandle.url`
  property. `run()`'s `Ctrl+C`/`SIGTERM` shutdown handler now logs any
  cron pinger(s) still running at that point, purely for visibility; it
  does not join or stop them.
- **Warn when `threads=` can't take effect.** `staypresent.run(threads=...)`
  only ever affects anything when `production=True` *and* `waitress` is
  actually installed. Passing a non-default `threads` value in any other
  case (`production=False`, or falling back to Flask's dev server because
  `waitress` isn't installed) is still accepted, but now logs a warning
  explaining that it has no effect, instead of silently doing nothing.

### Documentation

- Clarified in `README.md`/`DOCUMENTATION.md` that path normalization
  strips whitespace, that link/image/autolink escaping is applied exactly
  once (with a query-string example), the new `active_cron_handles()`/
  `CronHandle.url` API, and when a `threads=` value is silently ignored
  (now with a logged warning).
- No behavior changes to the renderer's intentionally-limited CommonMark
  scope (no footnotes/definition lists/math) or to `bot_module` not being
  validated for existence up front — both were already documented as
  deliberate design choices, not oversights, and remain so.

---

## 1.5.6 and earlier

See Git history.
