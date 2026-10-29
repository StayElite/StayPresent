# StayPresent — Changelog

## v1.7.1 [Current Release]

### Security & Sanitization
* **Markdown Link Scheme Sanitization:** Fixed a vulnerability in the built-in Markdown renderer where dangerous schemes enclosed in angle brackets (e.g. `[Click](<javascript:alert(1)>)`), obfuscated with percent-encoding (`%6a%61%76%61...`), or containing control characters bypassed scheme checks. Destinations are now normalized and unquoted before validation, stripping dangerous executable schemes (`javascript:`, `vbscript:`, `data:`, `file:`) safely.
* **Path Traversal & Null Byte Protection:** Enforced strict rejection of embedded null bytes (`\0`) in `staypresent.web._normalize_path()`.

### Fixed & Improvements
* **Boolean Type Coercion Bug Fixes:** Fixed subtle Python boolean-as-integer bugs across the entire codebase where booleans like `port=True`, `threads=True`, `max_restarts=True`, `restart_delay=True`, `heartbeat_timeout=True`, and `timeout=True` were incorrectly accepted as `1` or `1.0`:
  * `staypresent.runner.run()`: strictly validates `port`, `threads`, `max_restarts`, `restart_delay`, `restart_reset_after`, and `heartbeat_timeout` to reject booleans and non-numeric types.
  * `staypresent.pinger`: `_build_url()` and `ping()` / `cron()` now strictly disallow booleans for `port`, `timeout`, and `interval`.
* **Markdown Table Escaped Delimiters:** Fixed table cell parsing in `StayPresentMarkdownRenderer` where a literal escaped backslash before a pipe (`\\|`) was previously misinterpreted as an escaped pipe. Double backslashes are now treated as literal backslashes preceding column boundaries.
* **Service Parameter Validation:** `staypresent.service.restart()` now performs full type and format checks on parameters (`name`, `command`, `working_directory`, `restart_sec`, `enable_linger`) unconditionally across all policies, preventing invalid configurations from going unnoticed even when `policy="no"`.
* **Empty/Whitespace String Validation:** Fixed `status_registry._validate_optional_str()` and `runner.py`'s per-bot configuration to strictly reject empty or whitespace-only strings for `services_name` and `services_description`.
* **Test Suite Added:** Added comprehensive automated test suite in `tests/` covering pinger URL generation, markdown security sanitization, table parsing, service quoting & policies, web path normalization, and runner parameter validations.

---

## v1.7.0

### Added

* **Boot-level process persistence via systemd (`staypresent.restart()`):**
* Added OS-level process management using `systemctl --user` units on Linux to survive system reboots.
* Introduced policy support mirroring Docker syntax: `policy="always"`, `"on-failure"`, `"unless-stopped"`, and `"no"` (default).
* Implemented automated `loginctl enable-linger` registration to allow headless execution without active user sessions.
* *Note:* Returns the precise `systemctl --user start` command for manual invocation rather than auto-executing within the running script context to prevent duplicate processes.


* **Localized visitor timezones for status pages:**
* Extended `staypresent.web.status()` with a `timezone` parameter (defaults to `"auto"`).
* Client-side JavaScript now dynamically re-renders Unix timestamps using `Intl.DateTimeFormat` into the visitor's local browser timezone.
* Added support for explicit IANA timezone identifiers (e.g., `"Asia/Kolkata"`, `"America/New_York"`) and common standard aliases (`IST`, `UTC`, `GMT`, `EST`, `PST`).


* **Configurable time formatting:**
* Added `time_format` parameter (`"12h"` or `"24h"`, defaulting to `"12h"`) to `staypresent.web.status()` across incident logs, admin streams, and status indicators.



### Changed

* **BREAKING:** Restructured admin log entries in the JSON data endpoint from raw pre-formatted strings (`"14:32:10 [stderr]..."`) to structured JSON objects:
```json
{
  "time": 1773349200,
  "stream": "stderr",
  "line": "Connection refused",
  "display": "14:32:10 [stderr] Connection refused"
}

```


* Added raw Unix epoch timestamps (`"time"`) alongside formatted display strings (`"time_display"`) for all incident models in JSON endpoints.

### Fixed

* Fixed an issue where `web.text()`, `web.json()`, `web.html()`, and `web.markdown()` were missing `__doc__` attributes due to dynamic string concatenation at definition time.
* Resolved a potential status page date formatting bug by using `Intl.DateTimeFormat.formatToParts()` instead of string substitution.
* Fixed an issue where passing fractional floats to `restart_sec` in `staypresent.restart()` generated unit-less systemd configuration lines; explicit `s` duration suffixes are now applied.
* Added explicit validation to raise a `ValueError` when `sys.argv[0]` is empty (e.g., REPL or `python -c` execution) during `staypresent.restart()` invocation without an explicit `command`.
* Prevented uncaught `OSError` exceptions during `loginctl enable-linger` execution when system user lookup fails; failures now degrade gracefully to `WARNING` logs.
* Cleaned up unused internal signatures (`route_path` in `server.py`) and dead logic paths in `status_registry._display_name()`.

---

## v1.6.0

### Added

* **Automated Status Page (`staypresent.web.status()`):**
* Built-in `/status` web dashboard displaying system uptimes (24h, 7d, 30d, lifetime) and incident logs.
* Role-based access control splitting public health metrics from administrative outputs (`stdout`/`stderr` tails, exit codes) via `api_key` authentication.
* Built-in brute-force protection limiting administrative login attempts to 5 per 15-minute window.


* **Process Hang Detection:**
* Introduced `staypresent.heartbeat()` ping utilities alongside `heartbeat_timeout` configuration inside `staypresent.run()` to detect deadlocked process loops.


* **Execution Options:**
* Added `web_server=False` mode to manage process lifecycles without opening network sockets.
* Added support for standalone web server execution without process supervision.


* Extended static route handlers (`web.html()`, `web.markdown()`) with pattern-based file exclusions (`exclude=[...]`).

### Fixed

* Fixed URL generation for host strings containing explicit ports (e.g., `localhost:5000`).
* Added automatic bracket wrapping for raw IPv6 host literals (e.g., `[::1]:8080`).
* Fixed an issue where static directory route exclusions were not properly merged across overlapping paths.

### Changed

* Default paths (`/`, `/health`, `/status`) are now exposed consistently in route inspection APIs (`get_all()`, `paths()`).
* Subprocess IO streams now default to piped redirection to enable log capturing, setting `sys.stdout.isatty()` to `False` inside supervised scripts.

---

## v1.5.16

### Fixed

* Updated `staypresent.web.get()` and `get_all()` to return deep copies of internal state objects to prevent mutations across HTTP request cycles.
* Added eager validation for dictionary keys inside environment configuration to fail fast on non-string inputs.

---

## v1.5.15

### Fixed

* Standardized parent exit code resolution during concurrent subprocess failures to deterministically evaluate based on the lowest process index.

---

## v1.5.14

### Documentation

* Documented Markdown rendering constraints regarding reference-style links and multi-line blockquote formatting.

---

## v1.5.13

### Fixed

* Fixed a parsing error in fenced code blocks when language identifiers contained extended attribute strings (e.g., `python title="app.py"`).
* Fixed HTML structural alignment for nested lists containing block elements.

---

## v1.5.12

### Added

* Added rendering support for GitHub-Flavored Markdown task list items (`- [ ]` and `- [x]`).

---

## v1.5.11

### Fixed

* Resolved process shutdown hangs during restart sequences.
* Fixed Markdown header slug generation, parenthesis parsing, and signal handler chaining.