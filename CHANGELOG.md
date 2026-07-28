# Changelog

## 1.5.8

### Fixed

- **Markdown renderer: nested inline elements inside link text leaked raw
  placeholder tokens.** Code spans, escapes, and images are stashed as
  opaque placeholder tokens before links are processed; when one of those
  ended up inside a link's label, the link's own stashed value contained
  that nested token, but restoration only did a single forward pass
  (lowest index first), so a low-index token trapped inside a
  higher-index link's stash never got resolved. `[`code`](url)` rendered
  as `<a href="url">\x000\x00</a>`, and the very common "clickable
  badge/logo" pattern `[![alt](img.png)](url)` — found in countless
  READMEs — was affected the same way. Fixed by restoring placeholders in
  reverse (highest-index-first) order, since a stash can only ever embed
  a *lower*-index placeholder, so processing highest-index-first
  guarantees any nested token is exposed before its own turn comes up.
- **Markdown renderer: emphasis/bold/strikethrough inside link text was
  silently dropped.** `[**bold link**](url)` rendered the literal
  asterisks instead of `<strong>`, because a link's label gets embedded
  in its stashed `<a>...</a>` HTML *before* the main text's
  emphasis-processing step ever runs over it. Fixed by running
  emphasis/bold/strikethrough substitution directly over the label
  before it's embedded in the anchor tag.
- **`active_cron_handles()` lost "fire-and-forget" cron jobs almost
  immediately.** The cron registry tracked `CronHandle`s with a
  `weakref.WeakSet`, so if the caller didn't keep a strong reference to
  the handle returned by `cron()` — completely normal for a keep-warm
  pinger nobody intends to `.stop()` — the handle was garbage-collected
  right after `cron()` returned, and the job vanished from introspection
  even though its background thread kept running. Fixed by tracking
  handles with a plain set of strong references instead, removing an
  entry when `.stop()` is called and lazily pruning any whose thread has
  since exited whenever the registry is read.
- **Dead code in `pinger.py`.** `_ANY_HOSTS` included `""` as an
  "any host" alias, but `_build_url()` already raises `ValueError` for an
  empty/whitespace-only host earlier in the same function, so that
  branch could never be reached. Removed.
- **`staypresent.web.json()` didn't validate JSON-serializability until
  the first request.** A non-serializable payload only surfaced as a 500
  on the first incoming request, unlike every other `staypresent.web`/
  `staypresent.run()` argument, which all fail fast at call time.
  `json()` now attempts to serialize `data` immediately and raises
  `TypeError` right away if it can't.
- **`staypresent.web.markdown(favicon=...)` wasn't checked for existence
  up front.** Unlike `file_path`, a typo'd local `favicon` path silently
  404'd only once a browser actually requested it. A local (non-URL)
  `favicon` is now checked for existence at call time, the same way
  `file_path` already is, and raises `FileNotFoundError` immediately if
  missing.
- **`staypresent.run()` replaced any signal handler the host script had
  already installed, with no chaining.** Calling `signal.signal(SIGINT/
  SIGTERM, shutdown)` unconditionally discarded whatever handler the
  caller had set up before calling `run()`. `run()` now chains to any
  previously-installed handler — calling it after StayPresent's own
  cleanup completes — and accepts a new `install_signal_handlers=False`
  option to skip installing its own handlers entirely.
- **Calling `staypresent.run()` twice in one process failed with a
  generic, unhelpful error.** Because `run()` uses a single shared,
  module-level Flask app, a second call just tried to bind the same
  host:port again and failed with a bare "address already in use"
  `OSError`. `run()` now raises a specific `RuntimeError` up front if
  it's called more than once in the same process, explaining why and
  pointing at passing multiple bots to a single call instead.

### Documentation

- **New, prominent security callout for `staypresent.web.html()`/
  `staypresent.web.markdown()`:** registering a file at a path serves
  *every* file in that file's directory as a static-asset fallback — not
  just files actually referenced from the page. This was already
  documented in passing as "neighboring assets are served", but the
  scope (whole directory, not an allowlist of referenced files) was easy
  to miss; a `.env`, bot source file, or `.git/` sitting next to a served
  file would be downloadable by anyone who guesses the filename. Both
  docstrings and `README.md`/`DOCUMENTATION.md` now call this out
  explicitly, and `html()`/`markdown()` log a one-time warning per
  directory the first time it's exposed this way. This remains "working
  as designed" for this release — an opt-in allowlist is being
  considered for a future version.
- Documented the new `install_signal_handlers` parameter on
  `staypresent.run()`, the fail-fast behavior of `staypresent.web.json()`
  and `staypresent.web.markdown(favicon=...)`, and the specific error now
  raised when `run()` is called more than once.

---

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
