# StayPresent — Changelog

## 1.7.0 [Current Release]

### What's New

* **`staypresent.restart()` - restart on reboot, not just on crash (Linux):** Everything in StayPresent's own Crash Recovery Protocol only works while the Python process itself is alive - a full machine reboot kills that process (and every bot it was watching) outright, with nothing left running to restart anything. `staypresent.restart()` covers that gap by installing a real, OS-managed `systemctl --user` unit for your script, mirroring Docker's own `--restart` flag directly - the same four values, with the same default:

```python
staypresent.restart(policy="always")   # or "no" (default - does nothing), "on-failure"[:5], "unless-stopped"
staypresent.run("bot.py")
```

Defaults to `policy="no"`, same as Docker - a true no-op (nothing written, no `systemctl`/`loginctl` calls, no Linux check at all), so `staypresent.restart()` is safe to leave in a script unconditionally on any platform until you actually opt into a real policy. For `"always"`/`"on-failure"[:N]`/`"unless-stopped"`, it only installs and enables the unit - it never starts it immediately itself, since doing so from inside the very script already running right now would silently launch a second, independent copy alongside it; the exact `systemctl --user start ...` command to run yourself is returned and logged. Also attempts `loginctl enable-linger` automatically, so the unit can come back on every future boot without requiring an active login session (falls back to a `WARNING` with the manual command if that's not permitted on your system). `"unless-stopped"` has no exact systemd primitive (a manual `systemctl --user stop` doesn't durably persist across a later reboot the way Docker's does) - implemented as `Restart=always` with a `WARNING` logged every time it's used, spelling out exactly where it falls short. Linux (systemd) only; see [DOCUMENTATION.md](DOCUMENTATION.md#12-boot-level-restart-staypresentrestart) for the full policy-by-policy breakdown of how each one compares to - and differs from - real Docker behavior (`"on-failure"`'s `":N"` retry limit, for one, is a rolling-window rate limiter here rather than Docker's lifetime counter).

* **Status page timezone (`staypresent.web.status(timezone=...)`), defaulting to `"auto"` - each visitor's own browser-local time:** The status page's dates and times - incident timestamps, an admin's log-line timestamps, the "Last updated" indicator, and (when `copyright` is set) the copyright line's year - now render per-visitor by default: two people looking at the same page from different countries each see every timestamp in their own local zone, with zero configuration. Pass an explicit zone instead (`timezone="Asia/Kolkata"`, `timezone="UTC"`, ...) for a fixed, same-for-everyone timezone regardless of who's looking.

```python
staypresent.web.status(timezone="Asia/Kolkata")   # or the shorthand alias: timezone="IST" - default is "auto"
```

Accepts a standard [IANA zone key](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) (e.g. `"Asia/Kolkata"`, `"America/New_York"`, `"Europe/London"`) or one of a short list of common, low-ambiguity aliases: `IST`, `GMT`, `EST`/`EDT`, `CST`/`CDT`, `MST`/`MDT`, `PST`/`PDT`, `BST`, `CET`, `JST`, `AEST`. This is deliberately a short list — several familiar abbreviations genuinely mean different zones in different regions (`"IST"` alone could mean India, Israel, or Irish Standard Time), so each alias resolves to one specific, documented zone rather than guessing; anything else should be given as a real IANA key, which is always accepted as-is. An unrecognized alias or invalid IANA key raises `ValueError` immediately, at registration time.

A fixed zone (anything other than the `"auto"` default or `"UTC"`) requires Python 3.9+'s stdlib `zoneinfo` module (or the `backports.zoneinfo` package on older Pythons) - `"auto"`/`"UTC"` never need it.

**How `"auto"` actually works:** a fixed backend process can't resolve "the visitor's timezone" by itself - it has no visitor to ask until their browser has loaded the page. So the JSON data endpoint always includes both a raw Unix-epoch timestamp *and* a server-rendered fallback string (in UTC, for "auto") for every incident and admin log line - useful as-is for a script or `curl` hitting that endpoint directly - while the status page's own bundled JS re-renders every one of those raw timestamps in the browser's real local timezone (via `Intl.DateTimeFormat().resolvedOptions().timeZone`) and chosen `time_format` before displaying them.

* **New `time_format` parameter - 12-hour or 24-hour clocks, defaulting to 12-hour:**

```python
staypresent.web.status(time_format="24h")   # or "12h" (the default) - e.g. "14:30" vs "2:30 PM"
```

Applies everywhere `timezone` above does: incident timestamps, admin log lines, and the "Last updated" indicator. Raises `ValueError` for anything other than a recognized spelling of `"12h"`/`"24h"`.

### Breaking Changes

* **Admin log entries in the JSON data endpoint changed shape.** Previously each entry in a service's `"log"` array was a single pre-formatted string (e.g. `"14:32:10 [stderr] Connection refused"`). Each entry is now an object: `{"time": <epoch seconds>, "stream": "stdout"|"stderr", "line": "...", "display": "14:32:10 [stderr] Connection refused"}` - the raw fields let the status page itself re-render the timestamp in the visitor's local time/clock style, while `"display"` keeps a ready-to-use formatted string for anything reading the JSON directly. The bundled status-page JS handles both the old (string) and new (object) shapes defensively, in case a CDN or browser has a stale cached copy of the old JS talking to an upgraded server, or vice versa - but a custom integration reading `service.log` directly from the JSON should be updated for the new shape.
* Every incident in the JSON data endpoint now also includes its raw `"time"` (Unix epoch seconds) alongside the existing `"time_display"` string - purely additive, nothing removed.

### Bug Fixes & Improvements

* **`web.text()`/`web.json()`/`web.html()`/`web.markdown()` were silently missing their own docstrings.** Each of these builds its documentation by splicing shared parameter docs (`services_name`/`services_description`, `status`) into a larger block of text via string concatenation (`"""..."""  + _SHARED_DOC + """..."""`) — but Python only auto-populates a function's `__doc__` from a bare string *literal* as the very first statement in its body; a concatenation *expression* (even one that evaluates to a string) doesn't count; it's silently executed and discarded as a no-op statement instead. The result: `help(staypresent.web.text)` (and the equivalent for `json()`/`html()`/`markdown()`) returned nothing at all, despite each one having several hundred words of carefully written documentation sitting right there in the source — invisible to `help()`, IDE hover tooltips, and any documentation generator reading `__doc__`, for every release since these functions gained the shared-snippet pattern. Fixed by assigning each function's docstring explicitly (`text.__doc__ = "..."`) immediately after its definition — the standard, well-known workaround for exactly this Python behavior — rather than leaving it as a dead statement inside the function body. `staypresent.web.status()` was never affected (its docstring is a single literal, not a concatenation).
* Removed a second, smaller instance of the same class of issue this release's own `_display_name()` cleanup addressed: `server.py`'s `_render_status_page()` (and `_render_response()`, which only ever forwarded it along) accepted a `route_path` parameter that nothing inside either function actually used — dead weight left over from an earlier version, not affecting any output. Removed from both signatures and their one call site.
* Fixed a stale comment in `server.py` that still said the status page's timezone "default UTC" — the actual default has been `"auto"` since that feature shipped in this same release; the code itself was always correct, only the comment had drifted.
* **Dead-Code Cleanup:** Removed an unreachable branch (and an unused parameter) inside `status_registry._display_name()` (an unused `bot_id` parameter and a "Service (Unknown...)" fallback that could never actually be hit, since every real bot's `file_key` and every manually-registered `services_override` key are already guaranteed non-empty before that function is ever called). This was inert — it never changed what any status page actually rendered — but it was dead code sitting in an otherwise fully-exercised function, which is exactly the kind of thing that quietly rots or gets copy-pasted into a real bug later. Removed it and restored the plain, single-purpose implementation.
* While building the client-side timestamp re-rendering above, caught and fixed a display bug before it ever shipped: an incident's timestamp could show the date and year in the wrong order (e.g. "Aug 30 at 2025, 21:10 GMT+5:30" instead of "Aug 30, 2025 at 21:10 GMT+5:30"). The first version of that code did a plain text find-and-replace on the browser's locale-formatted string, which only ever touched the first comma it found rather than the one actually separating the date from the time. Rewritten to build the string directly from `Intl.DateTimeFormat`'s own structured `formatToParts()` output instead, which doesn't have this class of bug.
* **`staypresent.restart()` fixes found during a full-codebase review, before this ever shipped:**
  * A fractional `restart_sec` (e.g. `0.5`) was written into the systemd unit as a bare, unit-less number (`RestartSec=0.5`) — systemd's own documentation only guarantees unit-less numbers are parsed as whole seconds, not fractional ones. Now written with an explicit `s` suffix (`RestartSec=0.5s`), which is unambiguously correct for any value.
  * When `command` isn't given and `sys.argv[0]` is empty (e.g. a `python3 -c ...` one-liner, or certain embedders/REPL-like contexts), the old auto-derivation silently resolved to the *current working directory* rather than a script path (`os.path.abspath("")` returns the cwd) — producing a systemd unit that would only fail, confusingly, once actually started. Now raises a clear `ValueError` immediately, telling you to pass `command` explicitly instead.
  * The best-effort `loginctl enable-linger` step could raise an uncaught `OSError` (e.g. `getpass.getuser()` failing on a minimal system with no user database entry) *after* the systemd unit was already successfully installed and enabled — crashing the whole call over what should have been a soft, best-effort failure, same as every other lingering-related failure already is. Now caught and logged as a `WARNING` with the manual command to try, consistent with the rest of this step.

---

## 1.6.0

### What's New

* **Built-in Status Page (`staypresent.web.status()`):** You can now generate a real, auto-updating status page with a single function call. It includes a per-service list, rolling uptimes (24h, 7d, 30d, and lifetime), and a full incident history pulled directly from what StayPresent already tracks about your bots. If a metric isn't available, it's simply left off rather than shown as a fake placeholder.


```python
staypresent.web.status(
    title="Groundflare Bot Status",
    copyright="Groundflare Inc.",
    footer_links=[{"label": "Support", "url": "https://support.groundflare/support"}],
)

```


You don't even have to call it explicitly—a status page is now served at `/status` by default, right alongside `/health` and `/`. Use the function call only if you want to customize it or move it somewhere else.


The page separates public info (overall status, uptime, and friendly incident descriptions) from admin details (exit codes and recent stdout/stderr log tails) behind an `api_key`-gated login. If you leave the key unset, StayPresent automatically generates a random one for the session and logs it. You can also pass `api_key=""` to turn it off completely. Admin logins are rate-limited to 5 attempts per 15 minutes to protect against timing attacks, and you can enable `trust_proxy_headers=True` if you run behind a trusted reverse proxy.


* **Hang Detection (`staypresent.heartbeat()` & `run(heartbeat_timeout=...)`):** Crash detection used to only catch bots that actually exited, leaving frozen loops or deadlocked processes invisible. Now, you can sprinkle `staypresent.heartbeat()` inside your bot loops and set a `heartbeat_timeout` in `staypresent.run()`. If your bot stops checking in, StayPresent logs the issue, terminates the process, and handles it just like a regular crash.


* **New Modes for `staypresent.run()`:**
* Pass `web_server=False` to supervise a bot with full crash and restart management without running any HTTP server at all.


* Run `staypresent.run()` with no bot configured to spin up *only* the web server—ideal for dedicated status or health-check deployments.




* **File Exclusions for Static Routes:** When serving directories via `web.html()` or `web.markdown()`, you can now use `exclude=[".env", ".git", "*.py", "secrets.json"]` to block specific files, extensions, or glob patterns from being accessed. Any requests for excluded files will automatically return a clean 404.


* **Status Page Customization:** Every route function (`text()`, `json()`, `html()`, `markdown()`, `status()`) now accepts a `status=True/False` argument to control whether it gets its own row on the status page. Bots are shown by default unless you opt them out, and you can rename or describe rows using `services_name` and `services_description`.


* **Captured Bot Output:** Bot stdout and stderr are now captured rather than just dumped straight to the console. They are still echoed live to the parent process as expected, but they also feed a ring buffer that powers the status page's admin log tail and gives crash incidents extra context.



### Bug Fixes

* **Embedded Ports in Pings:** Fixed an issue where host strings containing ports (like `"localhost:5000"`) defaulted to `https` instead of `http` and broke when an explicit `port=` argument was also provided. Mismatches now log a warning and correctly reconcile before building the URL.


* **IPv6 URL Formatting:** IPv6 host literals (like `::1`) are now properly bracketed in generated URLs (e.g., `[::1]:8080`) to prevent parsing errors.


* **Unified Directory Exclusions:** If multiple routes served files out of the same directory, exclusions are now properly merged globally so security restrictions can't be bypassed via a secondary route.



### Changes

* **Virtual Default Routes:** `/`, `/health`, and `/status` are now served as implicit virtual defaults. They behave exactly as before, but functions like `get_all()` and `paths()` will now correctly list them instead of hiding them.


* **Subprocess Piping:** Bot subprocesses are now launched with piped output streams to support live log capture. Bots checking `sys.stdout.isatty()` will now see `False` instead of the parent terminal's value.



---

## 1.5.16

### Bug Fixes & Improvements

* **Independent State Copies:** `staypresent.web.get()` and `get_all()` now return deep copies of the internal state rather than live mutable references, preventing unintended modifications to future HTTP responses.


* **Early Validation for Environment Keys:** Non-string keys passed to `env` dictionaries now raise a clear, immediate validation error pointing directly to the problem instead of throwing deep subprocess tracebacks later.



---

## 1.5.15

### Bug Fixes

* **Deterministic Exit Codes:** When multiple bots fail simultaneously, the parent process now exits deterministically using the exit code of the lowest-indexed failing bot rather than relying on random thread-completion order.



---

## 1.5.14

### Documentation Updates

* Clarified the Markdown renderer's limitations, explicitly documenting that reference-style links (`[text][ref]`) are unsupported and that blockquote paragraphs must keep their leading `>` characters to avoid premature closure.



---

## 1.5.13

### Bug Fixes

* **Fenced Code Blocks:** Fixed an issue where code block info strings containing extra attributes or titles (like ````python title="app.py"`) broke the parser. The parser now correctly isolates the primary language class and ignores extra metadata.


* **Nested List Blocks:** Fenced code blocks, blockquotes, and headings nested inside list items now correctly nest inside their respective `<li>` elements instead of breaking the list apart.



---

## 1.5.12

### Improvements

* **Task Lists Support:** The built-in Markdown renderer now fully supports GitHub-Flavored-Markdown task lists (`- [ ]` and `- [x]`), rendering them as clean disabled checkboxes with proper CSS classes.



---

## 1.5.11 and Earlier

* Improved PyPI documentation links, resolved shutdown hangs during bot restarts, fixed Markdown heading slugs, URL sanitization, parenthesis handling, and signal-handler chaining.