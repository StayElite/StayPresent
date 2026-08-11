# StayPresent — Changelog

## 1.6.0 [Current Release]

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