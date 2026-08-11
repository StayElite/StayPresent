# StayPresent — Full Documentation

This is the complete reference for StayPresent: every parameter, every behavior, and every edge case. For a quicker overview, see [README.md](README.md).

## Table of Contents

1. [Requirements](#1-requirements)
2. [Getting Started](#2-getting-started)
3. [Web Server Configuration (`staypresent.web`)](#3-web-server-configuration-staypresentweb)
   - [3.1 Text Responses](#31-text-responses)
   - [3.2 JSON Responses](#32-json-responses)
   - [3.3 HTML & Static Assets](#33-html--static-assets)
   - [3.4 Markdown Responses](#34-markdown-responses)
   - [3.5 Status Pages (`staypresent.web.status`)](#35-status-pages-staypresentwebstatus)
   - [3.6 Naming Services (`services_name` / `services_description`)](#36-naming-services-services_name--services_description)
   - [3.7 Custom Paths & Multiple Responses](#37-custom-paths--multiple-responses)
   - [3.8 State Inspection](#38-state-inspection)
4. [Process Execution (`staypresent.run`)](#4-process-execution-staypresentrun)
   - [4.1 Running Multiple Bots](#41-running-multiple-bots)
   - [4.2 Bots Inside a Package (`bot_module`)](#42-bots-inside-a-package-bot_module)
   - [4.3 Hang Detection (`staypresent.heartbeat`)](#43-hang-detection-staypresentheartbeat)
   - [4.4 Running Without a Web Server, or Without Bots](#44-running-without-a-web-server-or-without-bots)
5. [Self-Ping / Keep-Warm (`staypresent.ping` / `staypresent.cron`)](#5-self-ping--keep-warm-staypresentping--staypresentcron)
6. [Built-in Defaults (`/`, `/health`, `/status`)](#6-built-in-defaults---health--status)
7. [The Built-in Markdown Renderer](#7-the-built-in-markdown-renderer)
8. [API Reference](#8-api-reference)
9. [Logging](#9-logging)
10. [Deployment Notes](#10-deployment-notes)
11. [FAQ](#11-faq)

---

## 1. Requirements

* **Python** 3.8+
* **Flask**
* **waitress** (optional, but highly recommended for production)

Every feature described in this document — including full Markdown rendering, tables, theming, and page metadata — works with these requirements alone. No additional package is needed for Markdown support; StayPresent ships its own renderer.

---

## 2. Getting Started

### Installation

Install the package via standard package managers.

**Standard Installation:**

```bash
pip install staypresent

```

**Production Installation (Recommended):**

To suppress development server warnings and utilize a production-grade WSGI server, install the `prod` extra. This automatically provisions `waitress`.

```bash
pip install staypresent[prod]

```

### Minimal Example

```python
import staypresent

staypresent.run("bot.py")

```

This is enough to:

1. Start a background web server on `0.0.0.0:8080` (using `waitress` if installed, otherwise Flask's dev server with a one-time warning).
2. Serve `{"message": "I'm Present"}` as JSON at `/`, `{"status": "ok"}` at `/health`, and a built-in status page at `/status`.
3. Launch `bot.py` as a subprocess and keep it running, automatically restarting it up to 5 times if it crashes.
4. Shut everything down cleanly on `Ctrl+C`/`SIGTERM`.

---

## 3. Web Server Configuration (`staypresent.web`)

The `staypresent.web` module dictates the HTTP response(s) served by the background web server. Every function accepts an optional `path` argument (default `"/"`), so you can host multiple independent responses at once — see [Section 3.7](#37-custom-paths--multiple-responses). If left unconfigured, `"/"` defaults to a JSON response (`{"message": "I'm Present"}`), `"/health"` defaults to `{"status": "ok"}`, and `"/status"` defaults to a built-in status page (see [Section 3.5](#35-status-pages-staypresentwebstatus)) — all three are implicit defaults, active until you register something else at that path.

**Basic Usage Example:**

```python
import staypresent

staypresent.web.json({
    "status": "running"
})

staypresent.run("bot.py")

```

### 3.1 Text Responses

Returns a `text/plain` response.

```python
import staypresent

staypresent.web.text("Service Operational")

```

**Signature:** `staypresent.web.text(message: str, path: str = "/", services_name: str = None, services_description: str = None, status: bool = False) -> None`

`services_name`/`services_description` and `status` are shared by every `staypresent.web.*()` function — see [Section 3.6](#36-naming-services-services_name--services_description) and [Section 3.5](#35-status-pages-staypresentwebstatus) respectively.

### 3.2 JSON Responses

Returns an `application/json` response. The dictionary/list you pass is deep-copied at call time, so mutating the original object afterwards does not change the live response — call `json()` again to update it.

```python
import staypresent

staypresent.web.json({
    "status": "online",
    "version": "1.2.0"
})

```

**Signature:** `staypresent.web.json(data: Any, path: str = "/", services_name: str = None, services_description: str = None, status: bool = False) -> None`

> **Note:** `data` is validated for JSON-serializability immediately, at call time — passing something that can't be serialized (e.g. a custom object with no JSON representation) raises `TypeError` right away, rather than only surfacing as a 500 error on the first incoming request.

### 3.3 HTML & Static Assets

Reads and serves an HTML file on every request. This allows for dynamic, on-disk updates without restarting the Python process.

```python
import staypresent

staypresent.web.html("templates/index.html")

```

**Signature:** `staypresent.web.html(file_path: str, path: str = "/", exclude: list = None, services_name: str = None, services_description: str = None, status: bool = False) -> None`

> **Note:** Any static assets (CSS, JS, images) located in the same directory as the target HTML file are automatically served. Path traversal is strictly prohibited by internal security checks (`send_from_directory` refuses to serve anything that would escape the target directory).
>
> ⚠️ **Security — this covers the whole directory, not just referenced assets.** "Automatically served" means *every* file inside `file_path`'s directory becomes reachable to anyone who requests it by name, not only the specific CSS/JS/image files actually linked from the page. If a `.env`, a bot's own source file, or a `.git/` directory happens to sit in that same directory, it's downloadable the same way. This is intentional — it's what makes relative asset links work without extra configuration — but the scope is easy to miss, so keep `file_path` in a directory containing only files you're comfortable serving publicly, or use `exclude` (below) to block specific files outright. StayPresent logs a one-time `WARNING` per directory (see [Section 9](#9-logging)) the first time `html()`/`markdown()` exposes it, as a reminder.

For any `path` other than the default `"/"`, a bare request to that path is redirected (HTTP 308) to a trailing-slash version — see [Section 3.7](#37-custom-paths--multiple-responses) for why this matters.

**Blocking specific files with `exclude`:**

```python
staypresent.web.html("template/index.html", exclude=[".env", ".git", "*.py", "secrets.json"])

```

`exclude` is a list of filename/extension/glob patterns that are never served out of `file_path`'s directory, regardless of any other route also serving that same directory — a request for a matching file gets a plain 404, the same as if it didn't exist. Matching rules:

* A plain extension like `".env"` is shorthand for the glob `"*.env"` — anything ending in `.env` is excluded.
* An entry already containing a wildcard (`*`, `?`, `[seq]`) is used exactly as given.
* Anything else (e.g. `"secrets.json"`) matches that exact filename.
* Matching is case-insensitive and applies at *any* depth under the directory, not just directly inside it — excluding `".git"` also blocks `sub/.git/config`, not only a top-level file literally named `.git`.
* An entry containing `/` (e.g. `"private/secret.txt"`) is matched against the whole relative path instead of a single filename, at any depth (so it also matches `a/private/secret.txt`).

If two or more `html()`/`markdown()` routes serve out of the *same* directory with different `exclude` lists, every request resolving to that directory is checked against the union of all of them — an exclusion set by any one route applies no matter which route's registration actually handles a given request.

### 3.4 Markdown Responses

Reads a `.md` file and renders it to clean, GitHub-styled HTML on every request — the same on-disk-editable model as `html()`. Rendering is handled entirely by StayPresent's own built-in renderer (see [Section 7](#7-the-built-in-markdown-renderer)); **no external package is required**.

```python
import staypresent

staypresent.web.markdown("CHANGELOG.md")

```

> ⚠️ **Security note:** `markdown()` serves neighboring static assets the exact same way `html()` does — see the callout in [Section 3.3](#33-html--static-assets). Everything in `file_path`'s directory becomes servable, not just files referenced from the rendered page, unless excluded via `exclude` (below).

**Signature:**

```python
staypresent.web.markdown(
    file_path: str,
    path: str = "/",
    mode: str = "auto",
    favicon: str = None,
    title: str = None,
    description: str = None,
    exclude: list = None,
    services_name: str = None,
    services_description: str = None,
    status: bool = False,
) -> None

```

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `file_path` | `str` | **Required** | Path to the `.md` file to serve. Must exist at call time (checked immediately — raises `FileNotFoundError` otherwise). |
| `path` | `str` | `"/"` | Route to host this page on. See [Section 3.7](#37-custom-paths--multiple-responses). |
| `mode` | `str` | `"auto"` | Color scheme for the rendered page. One of `"light"`, `"dark"`, or `"auto"`. Case-insensitive and whitespace-tolerant (`" Dark "` is accepted); `None` is treated the same as the default, `"auto"`. Anything else raises `ValueError`. |
| `favicon` | `str` or `None` | `None` | Adds a `<link rel="icon">` tag. A direct URL (`http://`, `https://`, or a protocol-relative `//...`) is used as-is. Any other value is treated as a relative path next to `file_path`, resolved the same way neighboring static assets already are — and, like `file_path` itself, its existence is checked immediately at call time, raising `FileNotFoundError` if it's missing, rather than silently 404ing only once a browser actually requests it. Must be a `str` or `None` — anything else raises `TypeError`. Also raises `ValueError` if `exclude` (below) would itself block the favicon from ever being served. |
| `title` | `str` or `None` | `None` | Sets `<title>` and an Open Graph `og:title` meta tag. Falls back to the Markdown file's own filename (e.g. `"guide.md"`) when omitted. Must be a `str` or `None`. |
| `description` | `str` or `None` | `None` | Adds a `<meta name="description">` tag and an `og:description` Open Graph tag — useful for link-preview cards on social platforms/chat apps. Must be a `str` or `None`. |
| `exclude` | `list` or `None` | `None` | Filename/extension/glob patterns to block from `file_path`'s directory. See [Section 3.3](#33-html--static-assets) for the matching rules — they're identical to `html()`'s. |
| `services_name` | `str` or `None` | `None` | Display name for this process's row on the status page. See [Section 3.6](#36-naming-services-services_name--services_description). Note this is distinct from `description` above — that one's the page's own `<meta name="description">`, this one's the status page's. |
| `services_description` | `str` or `None` | `None` | Description shown under that same status-page row. See [Section 3.6](#36-naming-services-services_name--services_description). |
| `status` | `bool` | `False` | Whether this route gets its own row on the status page. See [Section 3.5](#35-status-pages-staypresentwebstatus). |

**How `mode` affects the page:**

* `mode="auto"` (default): the page includes `<meta name="color-scheme" content="light dark">` and no forced theme attribute — the browser/OS decides via `prefers-color-scheme`, and the visitor's own preference wins.
* `mode="light"` / `mode="dark"`: the page includes `<meta name="color-scheme" content="light">` (or `"dark"`) and a `data-theme="light"`/`data-theme="dark"` attribute on the rendered `<article>`, forcing that theme for every visitor regardless of their own OS/browser setting.

**How `favicon` resolution works:**

```python
staypresent.web.markdown("docs/guide.md", path="/docs", favicon="favicon.png")

```

Here, `favicon.png` must exist in the same directory as `docs/guide.md` — checked immediately when `markdown()` is called, so a typo surfaces right away instead of only once a visitor's browser requests the icon. Once the page is served (at `/docs/`, after the trailing-slash redirect described in [3.7](#37-custom-paths--multiple-responses)), the browser requests `/docs/favicon.png`, which StayPresent resolves via the same static-asset lookup used for CSS/JS/images referenced from HTML/Markdown content.

```python
staypresent.web.markdown("docs/guide.md", favicon="https://example.com/icon.ico")

```

Here, the URL is inserted into the page as-is — no local file is needed, and no static-asset lookup happens.

**Full example:**

```python
import staypresent

staypresent.web.markdown(
    "docs/guide.md",
    path="/docs",
    mode="dark",
    favicon="favicon.png",
    title="Project Docs",
    description="Everything you need to get started.",
)
staypresent.run("bot.py")

```

### 3.5 Status Pages (`staypresent.web.status`)

`staypresent.web.status()` serves a built-in, auto-updating status page: a service list, rolling uptime percentages, and an incident history, all derived automatically from what StayPresent already observes about each bot (launches, crashes, restarts, hangs, permanent failures). Nothing on the page is fabricated — a metric StayPresent doesn't actually have (e.g. response time for a background bot that isn't itself an HTTP endpoint) is simply left off.

You don't have to call this at all: a status page is served at `/status` by default the moment you call `staypresent.run()`, the same way `/health` and `/` already have built-in defaults (see [Section 6](#6-built-in-defaults---health--status)). Call `status()` yourself to customize the title, theme, footer, or admin key, or to move it to a different path.

```python
import staypresent

staypresent.web.status(
    title="Groundflare Bot Status",
    copyright="Groundflare Inc.",
    footer_links=[{"label": "Contact Support", "url": "https://support.groundflare/support"}],
    api_key="a-long-random-secret",
    mode="dark",
)
staypresent.run("bot.py")

```

**Signature:**

```python
staypresent.web.status(
    title: str = None,
    path: str = "/status",
    copyright: str = None,
    footer_links: list = None,
    api_key: str = None,
    trust_proxy_headers: bool = False,
    mode: str = "auto",
    favicon: str = None,
    description: str = None,
    poll_seconds: float = 15,
    status: bool = False,
) -> None

```

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `title` | `str` or `None` | `None` | Page title/heading. Defaults to `"Service Status"`. |
| `path` | `str` | `"/status"` | Route to host the page on. Same trailing-slash redirect behavior as `html()`/`markdown()` for non-root paths, since the page's CSS/JS/data endpoint are served relative to it. |
| `copyright` | `str` or `None` | `None` | Footer copyright line (e.g. `"Groundflare Inc."` renders `"© <year> Groundflare Inc."`). Omitted entirely when not given; this is separate from, and doesn't replace, the "Powered by StayPresent" credit, which always appears. |
| `footer_links` | `list` or `None` | `None` | A list of `{"label": ..., "url": ...}` dicts shown as a row of footer links. Omitted entirely when not given. |
| `api_key` | `str` or `None` | `None` | Secret enabling the admin login (see below). Leave unset and StayPresent generates a random key for this process's lifetime and logs it at `INFO`, so the admin view works with zero setup; pass a fixed string for a key that survives a restart, or `api_key=""` to disable the admin view for this page entirely. |
| `trust_proxy_headers` | `bool` | `False` | If `True`, admin-login rate limiting uses the client IP from `X-Forwarded-For` instead of the raw TCP connection. Only enable this if a reverse proxy you control is guaranteed to sit in front of every request and sets/overwrites that header itself — otherwise a client can forge it to pin a lockout on someone else's IP. |
| `mode` | `str` | `"auto"` | Color scheme — `"light"`, `"dark"`, or `"auto"` (follows the visitor's OS/browser preference). Same meaning as `markdown()`'s `mode`. |
| `favicon` | `str` or `None` | `None` | Optional favicon. A direct URL (`http://`, `https://`, `//`, or `data:`) is used as-is; anything else is used as a plain `href`, so it must already be servable from somewhere (e.g. a path registered with `html()`) — unlike `markdown()`, there's no local file directory to resolve a relative filename against. Left unset, the page shows a small dot favicon that updates live to reflect overall status (green/amber/red); setting `favicon` disables that live color-swapping. |
| `description` | `str` or `None` | `None` | `<meta name="description">`/Open Graph description. Defaults to a generic `"<title> - live status, powered by StayPresent."` when omitted. |
| `poll_seconds` | `float` | `15` | How often (seconds) an open status page polls its own live data endpoint. Must be positive. Lower values mean fresher data at the cost of more requests from every open tab. |
| `status` | `bool` | `False` | Whether the status page itself gets a row *on* itself (labeled `"Status - Web"`). Doesn't affect whether the page works or is reachable — only whether it lists itself. |

**Public view vs. admin view:**

The page itself, its CSS/JS, and its live data endpoint are always visible to everyone, regardless of `api_key` — the same way a real status page's overall up/down state is public by design. What `api_key` gates is extra *technical* incident detail: the actual process exit code, and a recent stdout/stderr tail per service. A plain visitor still sees that an incident happened and its current status (e.g. "Service disruption detected — automatically recovering"), just described without exit codes or logs. An admin unlocks that detail via a small "Admin" link in the page's footer, entering the key either through the login form (which then sends it as an `X-API-Key` header) or by appending `?key=...` to the page URL.

Failed admin-login attempts are rate-limited per client IP: after 5 wrong keys within a 15-minute window, further attempts from that IP are rejected outright until the window passes. The key comparison itself uses a constant-time check, so a wrong guess's rejection speed can't be used to infer how many leading characters were correct.

**What the page shows:**

* **Service rows** — one per bot given to `staypresent.run()` (named after its own file/module by default; see [Section 3.6](#36-naming-services-services_name--services_description) to rename it), plus one per `staypresent.web.*()` route registered with `status=True`. Each row shows live status (operational/degraded/offline), uptime over 24h/7d/30d and lifetime, and a restart count.
* **Uptime chart** — a per-service uptime percentage chart, rendered client-side via Chart.js (loaded from a CDN — `cdn.jsdelivr.net` — so the status page itself requires outbound access to that host to render the chart; every other part of the page works with no external dependency).
* **Incident history** — a merged, most-recent-first feed of crashes, hangs, permanent failures, and recoveries across every visible service. Shows the most recent 20 by default; append `?history=1` to the page's data endpoint to fetch up to 200.

Bots hidden via `staypresent.run(status=False)` (or a `bots[i]['status']` override) don't get a row and don't contribute to the overall status or incident feed — they're still fully supervised, just not shown.

### 3.6 Naming Services (`services_name` / `services_description`)

By default, a bot's status-page row is named after its own file/module path, and the web server's row is expanded into one entry per `staypresent.web.*()` route registered with `status=True` (see [Section 3.5](#35-status-pages-staypresentwebstatus)). `services_name`/`services_description` override that default display name and add a description, shown under the name on the status page.

These can be set from whichever call is most convenient — the last one made for a given target always wins:

* **`staypresent.run(services_name=..., services_description=...)`** — only valid with zero or one bot configured process-wide (raises `TypeError` with more than one, since a plain string can't unambiguously name one of several bots). With no bot at all (`web_server=True`, no `bot_file`/`bot_module`/`bots`), this renames the web server's own row instead.
* **A `bots[i]` entry's own `"services_name"`/`"services_description"` keys** — the way to tag bots individually when there's more than one:

  ```python
  staypresent.run(bots=[
      {"file": "telegram_bot.py", "services_name": "Telegram Bot"},
      {"file": "discord_bot.py", "services_name": "Discord Bot", "services_description": "Community server"},
  ])

  ```

* **Any `staypresent.web.text()`/`json()`/`html()`/`markdown()` call's own `services_name`/`services_description`** — applies process-wide (there's no per-page variant), the same target `run()`'s own `services_name` would resolve to:

  ```python
  staypresent.web.markdown(
      "CHANGELOG.md",
      services_name="Telegram Bot",
      services_description="Customer chat support",
  )

  ```

A key that doesn't match any actual bot still gets its own row on the status page — useful for tracking an external dependency (e.g. a database, a third-party API) that StayPresent itself doesn't supervise. That row is always shown as "operational," since StayPresent has no live signal for something outside its own supervision.

### 3.7 Custom Paths & Multiple Responses

`text()`, `json()`, `html()`, `markdown()`, and `status()` all accept a `path` keyword argument. This lets a single StayPresent instance host several independent responses at once — useful for giving each of multiple bots (see Section 4.1) its own status endpoint.

```python
import staypresent

staypresent.web.json({"status": "online"}, path="/")
staypresent.web.text("bot #2 is alive", path="/bot2")
staypresent.web.html("dashboard.html", path="/dashboard")
staypresent.web.markdown("CHANGELOG.md", path="/changelog")

```

**Path rules:**

* A path is normalized: surrounding whitespace is stripped (so `" /status"` or `"/status "` — easy to introduce via copy-paste or an f-string — are treated the same as `"/status"` instead of silently registering an unreachable route), it must start with `/`, repeated slashes are collapsed, and a trailing slash is stripped (`"/status/"` and `"/status"` refer to the same route).
* Paths must not contain `?` or `#` — StayPresent raises `ValueError` if they do, since those characters belong in a query string/fragment, not a route.
* `path` must be a non-empty `str` — any other type raises `TypeError`, an empty/whitespace-only string raises `ValueError`.

**Static asset resolution and trailing slashes:**

* For `html()`/`markdown()` at any path other than `"/"`, a bare request to that path (e.g. `/dashboard`) is automatically redirected (HTTP 308) to a trailing-slash version (`/dashboard/`). This is required for relative asset links inside the file (`href="style.css"`, `src="images/logo.png"`, a relative `favicon`) to resolve against that file's own directory rather than its parent. `text()`/`json()` responses don't need this, since they have no static assets to resolve.
* Static asset lookups use the *longest matching path prefix* across every registered `html()`/`markdown()` route, so nested/overlapping mounts (e.g. `"/"` and `"/dashboard"` both hosting HTML/Markdown) resolve unambiguously to the right directory — a request for `/dashboard/style.css` is served from `dashboard.html`'s directory, not the root page's.
* Asset lookups use `send_from_directory` internally, which refuses to serve any path that would escape the target directory (no path traversal via `../`, absolute paths, etc.).

**Managing registered paths:**

```python
staypresent.web.paths()          # -> ['/', '/bot2', '/changelog', '/dashboard', '/health', '/status']
staypresent.web.get_all()        # -> {'/': {'type': 'json', 'value': {...}}, '/bot2': {...}, ...}
staypresent.web.get("/bot2")     # -> {'type': 'text', 'value': 'bot #2 is alive'}
staypresent.web.remove("/bot2")  # -> True (was registered) / False (wasn't)

```

`paths()` and `get_all()` include StayPresent's own implicit defaults (`/`, `/health`, `/status`) whenever they haven't been overridden by an explicit registration — see [Section 6](#6-built-in-defaults---health--status).

**Registering the same path more than once:**

`text()`/`json()`/`html()`/`markdown()`/`status()` always overwrite whatever was previously registered at their `path` — there's no error or refusal for reusing a path, since re-registering the *same* path is exactly how you update a live response (e.g. calling `json()` again with a fresh payload to refresh a status endpoint). That case stays completely silent.

What StayPresent does watch for is the response *type* at a path changing — e.g. a path held a `"json"` response and a later call registers `"text"` there instead. That's a much stronger signal that two different call sites (two different bots, or two unrelated parts of the same script) didn't realize they were both claiming the same path, and only the most recent one will ever be served. In that case, a `WARNING`-level log line is emitted through the `"staypresent"` logger (see [Section 9](#9-logging)) naming the path and both response types involved, so the collision is visible instead of silently serving the wrong thing. Nothing is blocked either way — the newest registration always wins — this only affects what gets logged.

### 3.8 State Inspection

To retrieve the currently configured response payload for debugging or testing:

```python
current_state = staypresent.web.get()
# Returns: {"type": "json", "value": {"status": "online", ...}}

```

`get()` defaults to `path="/"`; pass a different `path` to inspect any other registered route, including `/status` and `/health` even when nothing has been explicitly registered there — `get()` surfaces StayPresent's own implicit defaults the same way `get_all()`/`paths()` do (see [Section 6](#6-built-in-defaults---health--status)). For a Markdown entry, the returned dict also includes `mode`, `favicon`, `title`, and `description` keys; for a status-page entry, it includes `title`, `copyright`, `footer_links`, `api_key`, `mode`, and the rest of `status()`'s own fields.

Both `get()` and `get_all()` return an independent deep copy of the state — mutating the returned dict (including a nested `"value"` dict/list for a `"json"` entry) afterwards has no effect on what StayPresent actually serves. Call `json()`/`text()`/`html()`/`markdown()`/`status()` again to change the live response instead.


---

## 4. Process Execution (`staypresent.run`)

The `run` function is the primary entry point. It spawns the web server and concurrently executes one or more target Python scripts ("bots").

```python
import staypresent

staypresent.run(
    "bot.py",
    host="0.0.0.0",
    port=8080,
    threads=8
)

```

### 4.1 Running Multiple Bots

`bot_file` also accepts a list of paths, launching and independently supervising each one:

```python
import staypresent

staypresent.run(["telegram_bot.py", "discord_bot.py"])

```

`bot_args`/`env`, if given alongside a list, are applied identically to every bot in it. For per-bot arguments or environment variables, use `bots` instead — a list of dicts, one per bot:

```python
import staypresent

staypresent.run(bots=[
    {"file": "telegram_bot.py", "args": ["--verbose"]},
    {"file": "discord_bot.py", "env": {"SHARD": "0"}},
    {"file": "worker.py"},
])

```

`bots` is mutually exclusive with `bot_file`/`bot_args`/`env` — a `TypeError` is raised if both styles are mixed. Each entry in `bots` requires a `"file"` key; `"args"` (list) and `"env"` (dict) are optional per entry.

With multiple bots:

* Every bot file is validated to exist *before* the server starts (a missing file raises `FileNotFoundError` immediately, before anything is launched).
* If launching the very first attempt of any bot fails (e.g. bad interpreter, out of file descriptors), any bots already started are terminated first, and the failure is raised immediately to the caller — no leaked processes.
* Each bot gets its own restart counter and is monitored on its own thread — a crash (and subsequent restart) in one bot has no effect on the others.
* `staypresent.run()` waits for every bot to finish (or fail permanently) before returning or exiting the process.
* `Ctrl+C`/`SIGTERM` terminates the web server and *all* bot processes.
* Bots are tracked internally by their position in the list/`bots` array, not by filename — two bots can share the exact same filename (e.g. `shard_a/bot.py` and `shard_b/bot.py`) with no functional conflict whatsoever; each still gets its own process, its own restart counter, and its own independent supervision.

**Log labels for bots with the same filename:** every log line about a bot (crash, restart, giving up) identifies it with a label like `bot[0] 'worker.py'`. Normally that's just the filename. But if two or more bots in the same `run()` call share a filename, using just the filename there would make otherwise-distinct bots indistinguishable in the logs — two lines both reading `bot[0] 'bot.py' crashed` / `bot[1] 'bot.py' crashed` force you to cross-reference your own list order to know which is which. StayPresent detects this automatically: whenever a filename collides with another bot's in the same run, every bot sharing that filename is labeled with its full file path instead (e.g. `bot[0] 'shard_a/bot.py'` / `bot[1] 'shard_b/bot.py'`), so the logs stay unambiguous. Bots with a filename that doesn't collide with anything keep the shorter, plain filename label.

### 4.2 Bots Inside a Package (`bot_module`)

`bot_file` runs a bot the same way `python <file>` would from the command line — which breaks for a bot that's actually a module inside a package relying on package-relative imports (`from . import something`):

```
ImportError: attempted relative import with no known parent package

```

`bot_module` runs it the way `python -m <module>` would instead — exactly as if you'd typed that yourself from the project root:

```python
import staypresent

staypresent.run(bot_module="mypkg.bot")

```

It mirrors `bot_file` everywhere else:

* A single string or a list of strings, for one or several module-based bots.
* `bot_args`/`env` apply identically to every module in the list, same as with `bot_file`.
* In `bots`, use `"module"` instead of `"file"` per entry — and you can freely mix file-based and module-based bots in the same `bots` list:

```python
import staypresent

staypresent.run(bots=[
    {"file": "telegram_bot.py", "args": ["--verbose"]},
    {"module": "discord_bot.worker", "env": {"SHARD": "0"}},
])

```

**Rules and differences from `bot_file`:**

* `bot_module` is mutually exclusive with `bot_file` at the top level (`TypeError` if both are given); in `bots`, each entry must set exactly one of `"file"`/`"module"` (`TypeError` if both or neither are set).
* Unlike a file path, a module path is **not** checked for existence before the server starts. Verifying a module is importable safely requires actually importing it (running its parent packages' `__init__.py`), which `run()` deliberately avoids as a side effect in the orchestrating process. A missing or misspelled module therefore isn't caught up front the way a missing file is — instead, that bot process starts, Python itself reports `No module named '...'`, and it exits non-zero, which is then handled by the normal crash/restart logic like any other crash.
* The subprocess is launched with the same working directory as your orchestrating script (`staypresent.run()`'s caller) — so `bot_module="mypkg.bot"` needs to be resolvable from wherever you actually run your script, exactly like typing `python -m mypkg.bot` from that same location would.
* Log labels for module-based bots use the dotted module name (e.g. `bot[0] 'mypkg.bot'`). The same filename-collision handling from above applies to module names too — if two bots share the exact same module string, there's no more specific fallback than the module name itself (unlike a file path, a module name has no further-qualifying "directory" to fall back to), so those log lines are distinguished only by their `bot[i]` index.

### 4.3 Hang Detection (`staypresent.heartbeat`)

Crash recovery only ever catches a bot that actually *exits*. A bot that's still running but stuck — deadlocked, blocked forever on I/O, spinning in an infinite loop — never produces a non-zero exit code, so it's invisible to the crash/restart logic above no matter how long it sits there.

`staypresent.heartbeat()`, called periodically from inside your bot, closes that gap:

```python
# worker.py
import time
import staypresent

while True:
    staypresent.heartbeat()
    do_one_unit_of_work()
    time.sleep(1)

```

```python
# app.py
import staypresent

staypresent.run("worker.py", heartbeat_timeout=30)

```

If `worker.py` goes more than `heartbeat_timeout` seconds without calling `heartbeat()`, StayPresent logs it as "possibly hung," terminates the process, and hands it to the normal crash/restart handling described in [Crash Recovery Protocol](#crash-recovery-protocol) — the same way it would handle any other crash, just triggered by silence instead of a bad exit code. On the status page, this shows up as its own "unresponsive" incident, followed by the usual crash/restart trail.

`heartbeat_timeout` is `None` by default (no hang detection at all — a bot that never calls `heartbeat()` is never penalized unless you opt in). It's cheap enough to call on every iteration of a tight loop; there's no need to throttle it yourself. `staypresent.heartbeat()` is a harmless no-op when called outside a `heartbeat_timeout`-configured run (including when the script is run standalone, with no StayPresent supervision at all), so it's safe to leave in a bot that might run either way.

### 4.4 Running Without a Web Server, or Without Bots

Every combination of "bot(s)" and "web server" is valid except having neither:

* **Bot(s), no web server** — `staypresent.run("worker.py", web_server=False)`. Full crash/restart supervision, no HTTP server at all; `host`/`port`/`production`/`threads` are ignored (a non-default value for any of them logs a warning), and every `staypresent.web` registration is inert, since nothing is listening to serve it.
* **Web server, no bot(s)** — `staypresent.run()` with no `bot_file`/`bot_module`/`bots` given at all. Useful for a deployment that only needs to expose a status/health page, with no process for StayPresent itself to supervise.
* **Both** — the default, and everything documented elsewhere in this section.
* **Neither** (`web_server=False` with no bot configured) — raises `TypeError` immediately, since that combination would do nothing at all.

### Execution Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `bot_file` | `str` or `list[str]` | `None` | Target Python script(s) to execute concurrently, launched as `python <file> ...`. Mutually exclusive with `bot_module` and with `bots`. Optional as long as `web_server=True` — omit `bot_file`/`bot_module`/`bots` entirely to run the web server with no bot at all (see [Section 4.4](#44-running-without-a-web-server-or-without-bots)). |
| `bot_module` | `str` or `list[str]` | `None` | Dotted module path(s) to execute concurrently instead, launched as `python -m <module> ...`. See [Section 4.2](#42-bots-inside-a-package-bot_module). Mutually exclusive with `bot_file` and with `bots`. |
| `host` | `str` | `"0.0.0.0"` | Network interface to bind the web server. Ignored (with a warning if non-default) when `web_server=False`. |
| `port` | `int` | `8080` | Port allocation for the web server. Must be between 0 and 65535. Ignored (with a warning if non-default) when `web_server=False`. |
| `production` | `bool` | `True` | Utilizes `waitress` if available. Set to `False` to force Flask's dev server. Ignored (with a warning if non-default) when `web_server=False`. |
| `threads` | `int` | `4` | Worker threads for `waitress` (requires `production=True` *and* `waitress` actually installed). Must be at least 1. If it can't take effect — `production=False`, `waitress` isn't installed, or `web_server=False` — a non-default value is silently accepted but has no effect on the resulting server; a warning is logged in that case so the mismatch shows up in your logs rather than looking like it worked. |
| `restart_on_crash` | `bool` | `True` | Relaunches a bot upon a non-zero exit code. |
| `max_restarts` | `int` | `5` | Maximum consecutive restart attempts, per bot. Must be `>= 0`. |
| `restart_delay` | `float` | `2.0` | Seconds to wait before process respawn. Must be `>= 0`. This wait is interruptible: a `Ctrl+C`/`SIGTERM` arriving during it wakes the bot's monitor thread immediately instead of only after the full delay elapses, so shutdown isn't held up waiting out a restart backoff — see the note on shutdown ordering below.
| `restart_reset_after` | `float` | `60.0` | Seconds of continuous uptime required to reset a bot's crash counter to zero. Must be `>= 0`. |
| `heartbeat_timeout` | `float` or `None` | `None` | Seconds a bot may go without calling `staypresent.heartbeat()` before it's treated as hung, terminated, and handed to the normal crash/restart logic. `None` (default) disables hang detection entirely. Must be `> 0` if given. See [Section 4.3](#43-hang-detection-staypresentheartbeat). |
| `bot_args` | `list` | `None` | CLI arguments to pass to every bot in `bot_file`/`bot_module` (e.g., `["--verbose"]`). Must be a list, not a bare string. Ignored when `bots` is used, and has no effect (with a warning) if no bot is configured at all. |
| `env` | `dict` | `None` | Environment variables injected into every bot in `bot_file`/`bot_module`, merged over the current process's environment. Keys must be strings (values are coerced to strings automatically). Ignored when `bots` is used, and has no effect (with a warning) if no bot is configured at all. |
| `bots` | `list[dict]` | `None` | Per-bot configuration: `[{"file": ..., "args": [...], "env": {...}, "services_name": ..., "services_description": ..., "status": ...}, {"module": ...}, ...]`, each with exactly one of `"file"`/`"module"` — `"args"`, `"env"`, `"services_name"`, `"services_description"`, and `"status"` are all optional per entry. Mutually exclusive with `bot_file`/`bot_module`/`bot_args`/`env`. |
| `install_signal_handlers` | `bool` | `True` | Whether `run()` installs its own `SIGINT`/`SIGTERM` handlers for graceful shutdown. When `True`, any handler your own script already registered for those signals *before* calling `run()` is chained: `run()`'s handler runs its own cleanup (terminating bot processes, logging active cron pingers) first, then calls your previously-installed handler afterward, rather than silently discarding it. Set to `False` to skip installing StayPresent's handlers entirely — useful if your script wants full, exclusive control over shutdown signaling. |
| `web_server` | `bool` | `True` | Whether to start the background web server at all. `False` runs bot(s) only — see [Section 4.4](#44-running-without-a-web-server-or-without-bots). Requires at least one bot; `web_server=False` with no bot configured raises `TypeError`. |
| `services_name` | `str` or `None` | `None` | Display name for this call's one bot (or the web server's own row, if no bot is configured) on the status page. Only valid with zero or one bot configured process-wide — see [Section 3.6](#36-naming-services-services_name--services_description). |
| `services_description` | `str` or `None` | `None` | Description shown under that same status-page row. Same single-bot-only rule as `services_name`. |
| `status` | `bool` | `True` | Whether the bot(s) this call configures get their own row on the status page. Defaults to `True` (shown unless turned off) — the opposite default from every `staypresent.web.*()` route's own `status=`. Override per bot via that bot's own `bots[i]['status']`. Has no effect on the web server's own row. |

> **Note on calling `run()` twice:** `run()` uses a single, shared, module-level Flask app (`staypresent.server.app`), so it's designed to be called exactly once per process. A second call raises `RuntimeError` immediately, explaining the issue and pointing at passing every bot to one `run()` call instead (via `bot_file`/`bot_module` as a list, or via `bots`) — see [Section 4.1](#41-running-multiple-bots). Without this check, a second call would instead fail later with a generic `OSError: [Errno 98] Address already in use` from trying to bind the same `host`/`port` twice, with no indication of the real cause. This "already called" state is only claimed once every argument above has passed validation and the server is actually about to start — a *first* call that fails validation (a missing bot file, an out-of-range `port`, etc.) never claims it, so it doesn't stand in the way of a later, valid call; you'll always see the real error from whichever call is actually invalid, not a misleading "already called" error from a later one.

### Crash Recovery Protocol

StayPresent strictly monitors every bot's subprocess lifecycle, independently:

* **Clean Exits:** An exit code of `0` is treated as an intentional shutdown for that bot and bypasses restart logic.
* **Hangs:** A bot that's still running but has stopped doing anything is not, by itself, caught by any of the exit-code-based rules below — see [Hang Detection](#43-hang-detection-staypresentheartbeat) (`heartbeat_timeout`) for the opt-in mechanism that catches this case and feeds it into the same restart logic as a crash.
* **Signals:** Interruptions (`SIGINT`/`Ctrl+C`, `SIGTERM`) initiate a clean teardown of the server and every bot. If your own script already installed a handler for `SIGINT`/`SIGTERM` before calling `run()`, it's chained — called after StayPresent's own cleanup finishes, not silently replaced (see `install_signal_handlers` in the parameter table above). Signal handlers can only be registered on the main thread — if `run()` is called from elsewhere, a warning is logged and graceful signal handling is skipped rather than crashing. A signal arriving while a bot is in its `restart_delay` backoff (waiting to respawn after a crash) is handled safely: shutdown and the pending respawn are synchronized so exactly one of them wins — either the respawn is cancelled before it happens, or shutdown terminates the freshly-respawned process too - so a shutdown can never leave an untracked, un-terminated bot process running.
* **Consecutive-Crash Budget:** `max_restarts` counts *consecutive* crashes. If a bot stays up for at least `restart_reset_after` seconds after a restart, its counter resets to 0 — so a long-running bot that occasionally crashes once isn't penalized for crashes from long ago.
* **Terminal Failures:** If `max_restarts` is exhausted for a bot, or if restarts are disabled and it crashes, that bot is marked as permanently failed (but other bots keep running). Once every bot has finished, if any bot ended in a permanently-failed state, `staypresent.run()` exits the main process with a non-zero exit code, so platform-level orchestrators (Docker, systemd, Render, Railway) correctly detect the failure and can apply their own restart policy. When more than one bot fails, the process's own exit code is deterministically the lowest-indexed failing bot's own exit code (not whichever bot's monitor thread happened to finish first).
* **Relaunch Failures:** If the OS itself refuses to spawn a replacement process during a restart (out of file descriptors/memory, a process-count ulimit, etc.), that's treated as a terminal failure for that bot rather than crashing the monitor thread.

Every one of these transitions — a start, a crash, a hang, a permanent failure, a clean exit, a recovery — is also recorded for the status page described in [Section 3.5](#35-status-pages-staypresentwebstatus), if you're using it. This tracking runs regardless of whether you've called `staypresent.web.status()` at all; it costs nothing extra either way.

---

## 5. Self-Ping / Keep-Warm (`staypresent.ping` / `staypresent.cron`)

Some free-tier hosts spin a service down after a period of inactivity, even with an open HTTP port. `staypresent.ping()` and `staypresent.cron()` are optional helpers for periodically hitting your own public URL to prevent that — nothing is pinged unless you call one of these yourself.

### `staypresent.ping(...)`

Sends a single synchronous HTTP GET request and reports the result.

```python
import staypresent

result = staypresent.ping("https://my-bot.onrender.com")
# {'url': 'https://my-bot.onrender.com/', 'ok': True, 'status_code': 200, 'elapsed': 0.42, 'error': None}

```

**Signature:** `staypresent.ping(host: str, port: int = None, path: str = "/", timeout: float = 10.0, https: bool = None) -> dict`

| Parameter | Description |
| --- | --- |
| `host` | A bare hostname/IP, `"host:port"`-style string, or a full URL (`"https://..."`). If a full URL is given, `port`/`path`/`https` are ignored (and a warning is logged if you passed non-default values for them anyway). `"0.0.0.0"`/`"::"` are treated as `"127.0.0.1"`, since they're bind addresses rather than something you can send an outgoing request to. |
| `port` | Port to connect to (1–65535). Ignored if `host` is a full URL. |
| `path` | URL path to request. Ignored if `host` is a full URL. |
| `timeout` | Seconds to wait for a response before giving up. Must be `> 0`. |
| `https` | Force `https` (`True`) or `http` (`False`). If omitted: defaults to `https` for anything that isn't a local address, and `http` for `"127.0.0.1"`/`"localhost"`/`"::1"` — matching what `staypresent.run()` itself serves locally. |

**Return value:** a dict with keys `url`, `ok` (`True` for any 2xx/3xx response), `status_code`, `elapsed` (seconds, rounded to 3 decimals), and `error` (a short description on failure — HTTP error status, timeout, DNS failure, connection refused, etc. — otherwise `None`).

### `staypresent.cron(...)`

Starts a background thread that repeatedly calls `ping()` on a schedule.

```python
import staypresent

handle = staypresent.cron("https://my-bot.onrender.com", interval=300)  # every 5 minutes

```

**Signature:**

```python
staypresent.cron(
    host: str,
    port: int = None,
    path: str = "/",
    interval: float = 300.0,
    repeat: bool = True,
    timeout: float = 10.0,
    https: bool = None,
    on_success=None,
    on_failure=None,
) -> CronHandle

```

| Parameter | Description |
| --- | --- |
| `host`, `port`, `path`, `https` | Same as `ping()` — describe the URL to hit. Validated immediately (raises on bad input) rather than failing silently on the first tick. |
| `interval` | Seconds between pings. Must be `> 0`. |
| `repeat` | If `True` (default), pings forever until stopped. If `False`, pings exactly once. |
| `timeout` | Per-request timeout in seconds, same as `ping()`. |
| `on_success` | Optional `fn(result)` called after each successful ping. An exception raised inside it is logged and swallowed — it never kills the background thread. |
| `on_failure` | Optional `fn(result)` called after each failed ping. Same exception-safety as `on_success`. |

**Returns:** a `CronHandle`:

```python
handle.stop(wait: bool = False, timeout: float = None)  # stop the background pinger; safe to call more than once
handle.is_running                                       # property: True/False
handle.url                                              # property: the URL this cron job pings

```

Cron pingers run on daemon background threads, so they're never registered with `staypresent.run()`'s own shutdown handling the way bot processes are — in practice this doesn't matter, since daemon threads are torn down automatically when the process exits. If you do want visibility into what's still active (e.g. for your own logging), `staypresent.active_cron_handles()` returns every currently-running `CronHandle` from any past call to `cron()`:

```python
import staypresent

for handle in staypresent.active_cron_handles():
    print(handle.url, handle.is_running)

```

> **Note:** `active_cron_handles()` finds a `CronHandle` regardless of whether you kept a reference to it yourself — including the common "fire-and-forget" pattern where the return value of `cron()` is discarded entirely (e.g. `staypresent.cron("https://my-bot.onrender.com")` with no assignment) for a keep-warm pinger you never intend to `.stop()`. The registry holds its own reference to every handle until that handle's `.stop()` is called (or its background thread has otherwise exited), so a discarded return value never causes the job to silently disappear from introspection.

`staypresent.run()` itself calls this during its `Ctrl+C`/`SIGTERM` shutdown sequence and logs any cron pinger(s) still running at that point, purely for visibility — it does not stop or wait on them; they're daemon threads and exit with the process regardless.

---

## 6. Built-in Defaults (`/`, `/health`, `/status`)

Three paths are served automatically the moment the web server starts, unless you register something of your own there:

| Path | Default response |
| --- | --- |
| `/` | `{"message": "I'm Present"}` (JSON) |
| `/health` | `{"status": "ok"}` (JSON) — useful for platform health-check probes and uptime monitors that expect a dedicated path separate from your regular response(s). |
| `/status` | A full status page — see [Section 3.5](#35-status-pages-staypresentwebstatus). |

These are *defaults*, not *reservations*: if you register your own response at any of the three via `staypresent.web.text()`/`json()`/`html()`/`markdown()`/`status()`, your response is served there instead, and the built-in default is simply never reached. `staypresent.web.get()`, `get_all()`, and `paths()` all report these three paths as active even when nothing has been explicitly registered at them, since a real response genuinely is being served there.

---

## 7. The Built-in Markdown Renderer

`staypresent.web.markdown()` uses a Markdown-to-HTML renderer that ships with StayPresent itself — no `markdown` package or any other dependency is installed or required. It supports the constructs people actually use in READMEs, changelogs, and docs:

* **Headings** — both ATX (`# Heading`) and Setext (`Heading\n===` / `Heading\n---`) styles, levels 1–6. Each heading gets a stable, GitHub-compatible `id` slug (lowercased, punctuation stripped, spaces turned into hyphens, de-duplicated with a numeric suffix on repeats) for anchor links — computed from the heading's *rendered* text, so a heading containing a link, image, or emphasis (e.g. `## [Docs](url) Guide`) slugs from "Docs Guide", not from the raw, unstripped Markdown source (which would otherwise fuse the link's URL into the id).
* **Emphasis** — `**bold**`/`__bold__`, `*italic*`/`_italic_`, `***bold italic***`, and `~~strikethrough~~`.
* **Inline code** — `` `code` `` (including multi-backtick spans like ` ``code with a ` backtick`` `).
* **Links & images** — `[text](url "optional title")` and `![alt](url "optional title")`, plus bare autolinks (`<https://example.com>`). A destination may contain one level of balanced parens (e.g. `https://en.wikipedia.org/wiki/Foo_(bar)`) without being truncated at the inner `)`.
* **Lists** — unordered (`-`, `*`, `+`) and ordered (`1.`), including nested lists (bullet-in-numbered and numbered-in-bullet nesting both work correctly), multi-paragraph list items, and GitHub-style tight/loose rendering (a list with a blank line between any two items wraps every item's text in `<p>`; one without doesn't). An ordered list that starts at a number other than 1 (e.g. `5. five`) renders with the matching `start` attribute. A list item can also contain other nested block content indented under it — a fenced code block, a blockquote, or a heading — which is common in step-by-step instructions (e.g. a numbered step followed by an indented ` ``` ` code example). **Task lists** (`- [ ] todo`, `- [x] done`) render as a disabled, GitHub-styled checkbox (checked for `[x]`/`[X]`) rather than literal `[ ]`/`[x]` text — only when the marker is the very first thing in the item (matching GFM), so a stray `[ ]` mid-sentence is left alone.
* **Blockquotes** — including nested blockquotes.
* **Code blocks** — both fenced (` ``` ` or `~~~`, with a language tag for a `class="language-xxx"` hook — only the first word of the fence's info string is used for this, so ` ```python title="app.py" ` still highlights as Python, with the rest of the info string simply ignored) and indented (4-space/tab) code blocks.
* **Tables** — GitHub-flavored pipe tables, including column alignment (`:--`, `--:`, `:-:`). A table's header row is recognized as its own block even when it directly follows a paragraph line with no blank line in between (matching GitHub's own behavior) — `intro line\n| a | b |\n|---|---|` renders the intro as a `<p>` followed by a separate `<table>`, rather than folding the table's pipe-delimited rows into the paragraph as literal text.
* **Horizontal rules** — `---`, `***`, `___`.
* **Hard line breaks** — a line ending in two-or-more spaces, or a trailing backslash.
* **Raw HTML passthrough** — a line starting with a recognized block-level HTML tag (e.g. `<p align="center">...`) or an HTML comment is passed through verbatim, unescaped — the same "HTML block" behavior CommonMark/GitHub use, which is what makes centered logo/badge headers at the top of a README work correctly.
* **Backslash escapes** — `\*`, `\_`, `` \` ``, etc. for literal punctuation.

Everything else (plain text, and any of the constructs above) is HTML-escaped before rendering, so Markdown source containing `<`, `>`, `&`, or literal `<script>` tags cannot inject markup into the page — only recognized raw-HTML blocks are passed through, and even those are limited to a fixed list of known block-level tag names.

Escaping is applied exactly once per character, including inside link/image URLs and titles and inside autolinks — so a URL with a query string like `[docs](https://example.com/x?a=1&b=2)` renders as `href="https://example.com/x?a=1&amp;b=2"` (a single, correctly-escaped `&amp;`), not a mangled `&amp;amp;b=2`, and an autolink like `<https://example.com/x?a=1&b=2>` keeps its full URL instead of being truncated at the `&`.

**Link/image URLs are checked against a scheme blocklist**, independent of the HTML-escaping above (escaping neutralizes markup injection; this neutralizes an *executable* destination). `javascript:`/`vbscript:` (run arbitrary script directly) and `file:` (local filesystem access) are rejected for both links and images; `data:` (which can smuggle a full HTML document, script and all, into a click) is additionally rejected for links specifically. A rejected URL falls back to plain, already-escaped text — `[click me](javascript:alert(1))` renders as the plain text `click me`, not a working link — while ordinary `http(s)://`, relative (`/path`, `./file`), and anchor (`#section`) URLs, and `data:` *images* (a common, inert way to embed a small icon inline), are unaffected.

**Nested inline content inside link/image text** — code spans, emphasis/bold/strikethrough, and images all work correctly when nested inside a link's text, including the very common "clickable badge/logo" README pattern:

```markdown
[`code`](https://example.com)
[**bold link**](https://example.com)
[![badge](badge.svg)](https://example.com)

```

renders as:

```html
<a href="https://example.com"><code>code</code></a>
<a href="https://example.com"><strong>bold link</strong></a>
<a href="https://example.com"><img src="badge.svg" alt="badge"></a>

```

Internally, code spans/escapes/images are protected from further processing by being replaced with an opaque placeholder token before links are parsed, then restored afterward — restoration happens in reverse (highest-placeholder-index-first) order, since a placeholder can only ever have a *lower*-index placeholder nested inside it (never a higher one), which is what lets a placeholder trapped inside a link's own stashed HTML resolve correctly instead of leaking a raw `\x00N\x00` token into the page. A link's text also goes through emphasis/bold/strikethrough substitution directly (not just the surrounding page text), so `**bold**` inside link text renders as `<strong>`, not literal asterisks.

### Styling

Rendered Markdown is wrapped in `<article class="markdown-body">` and styled with a bundled stylesheet closely modeled on GitHub's own `.markdown-body` styles — headings, tables, code blocks, blockquotes, and images all get sensible, familiar styling with no configuration needed. The stylesheet supports:

* **`prefers-color-scheme`-based automatic dark mode** when `mode="auto"` (the default) — no code needed on your end, it's built into the shipped CSS.
* **Forced light/dark** via a `data-theme="light"`/`data-theme="dark"` attribute when you pass `mode="light"`/`mode="dark"` to `staypresent.web.markdown()`.

### What it intentionally does not do

This is a lightweight renderer, not a full CommonMark implementation. It does not support: footnotes, definition lists as a distinct syntax (beyond raw HTML passthrough), custom containers/admonitions, LaTeX/math rendering, reference-style links/images (`[text][ref]` + `[ref]: url` elsewhere in the document — only the inline `[text](url)` form works), or blockquote "lazy continuation" (a paragraph line inside a `>` blockquote that omits the leading `>` ends the blockquote there rather than continuing it, unlike CommonMark's own more permissive rule). For any of these, render your Markdown to HTML with a different tool ahead of time and serve the result with `staypresent.web.html()` instead.

---

## 8. API Reference

### `staypresent.web`

* **`web.text(message: str, path: str = "/", services_name: str = None, services_description: str = None, status: bool = False)`** – Configures `path` to return plain text.
* **`web.json(data: Any, path: str = "/", services_name: str = None, services_description: str = None, status: bool = False)`** – Configures `path` to return a JSON payload (deep-copied).
* **`web.html(file_path: str, path: str = "/", exclude: list = None, services_name: str = None, services_description: str = None, status: bool = False)`** – Configures `path` to serve an HTML file, read fresh every request, alongside neighboring static files (except any matching `exclude`).
* **`web.markdown(file_path: str, path: str = "/", mode: str = "auto", favicon: str = None, title: str = None, description: str = None, exclude: list = None, services_name: str = None, services_description: str = None, status: bool = False)`** – Configures `path` to serve a Markdown file rendered to styled HTML, read and re-rendered fresh every request, alongside neighboring static files (except any matching `exclude`). See [Section 3.4](#34-markdown-responses).
* **`web.status(title: str = None, path: str = "/status", copyright: str = None, footer_links: list = None, api_key: str = None, trust_proxy_headers: bool = False, mode: str = "auto", favicon: str = None, description: str = None, poll_seconds: float = 15, status: bool = False)`** – Configures `path` to serve the built-in status page. See [Section 3.5](#35-status-pages-staypresentwebstatus).
* **`web.remove(path: str = "/")`** – Stops hosting a response at `path`. Returns `True`/`False`.
* **`web.get(path: str = "/")`** – Returns the currently configured response state for `path` as a dictionary, including StayPresent's own implicit defaults at `/`, `/health`, and `/status`, or `{}` if nothing is registered or defaulted there.
* **`web.get_all()`** – Returns every path currently hosting a response — including the implicit defaults above — and its state, as one dictionary.
* **`web.paths()`** – Returns a sorted list of every path currently hosting a response, including the implicit defaults above.

### `staypresent`

* **`run(bot_file: str | list[str] = None, bot_module: str | list[str] = None, host: str = "0.0.0.0", port: int = 8080, production: bool = True, threads: int = 4, restart_on_crash: bool = True, max_restarts: int = 5, restart_delay: float = 2.0, restart_reset_after: float = 60.0, heartbeat_timeout: float = None, bot_args: list = None, env: dict = None, bots: list[dict] = None, install_signal_handlers: bool = True, web_server: bool = True, services_name: str = None, services_description: str = None, status: bool = True)`** – Starts the HTTP server, your bot process(es), or both. Raises `RuntimeError` if called more than once in the same process, and `TypeError` if given neither a bot nor `web_server=True` — see the notes in [Section 4](#4-process-execution-staypresentrun).
* **`heartbeat()`** – Call from inside a bot to signal it's still alive; only meaningful when the parent `run()` call set `heartbeat_timeout`. See [Section 4.3](#43-hang-detection-staypresentheartbeat).
* **`ping(host: str, port: int = None, path: str = "/", timeout: float = 10.0, https: bool = None) -> dict`** – Sends a synchronous HTTP request.
* **`cron(host: str, port: int = None, path: str = "/", interval: float = 300.0, repeat: bool = True, timeout: float = 10.0, https: bool = None, on_success=None, on_failure=None) -> CronHandle`** – Runs scheduled background keep-warm requests.
* **`active_cron_handles() -> list[CronHandle]`** – Returns every currently-running `CronHandle` from any past call to `cron()`. See [Section 5](#5-self-ping--keep-warm-staypresentping--staypresentcron).

---

## 9. Logging

StayPresent logs through its own `"staypresent"` logger, configured with a single dedicated `StreamHandler` and `logger.propagate = False`. It deliberately never calls `logging.basicConfig()` or otherwise touches the *root* logger, so it won't clobber, duplicate, or reformat log output your bot script has already configured for its own, unrelated loggers.

You'll see log lines for:

* Web server startup (`waitress` vs. the Flask dev-server fallback, and which host/port it bound to) — or, with `web_server=False`, a line noting no web server is being started.
* Each bot process starting, crashing, restarting, exhausting its restart budget, going unresponsive (see [Hang Detection](#43-hang-detection-staypresentheartbeat)), or exiting cleanly.
* Signal-triggered shutdowns (`SIGINT`/`SIGTERM`), and a previously-installed handler being chained afterward, if any.
* Unexpected web-server thread failures (both at startup and later during the run).
* Cron pinger start/stop events (at `INFO`) and individual failed pings (at `WARNING`, via `ping()`'s own logging).
* A one-time `WARNING` per directory the first time `web.html()`/`web.markdown()` exposes it as a static-asset fallback — see the security note in [Section 3.3](#33-html--static-assets).
* The auto-generated admin key for a status page with no `api_key` given, at `INFO` — see [Section 3.5](#35-status-pages-staypresentwebstatus).

Each bot's own stdout/stderr output continues to print to the console exactly as it did before — it's captured (to feed the status page's log tail) and echoed, not redirected or silenced.

If you want to adjust the log level or attach your own handler, grab the logger directly:

```python
import logging

logging.getLogger("staypresent").setLevel(logging.DEBUG)

```

---

## 10. Deployment Notes

* **Render / Railway / Koyeb / Heroku:** these platforms typically require your service to bind an HTTP port and respond to requests to be considered "healthy". `staypresent.run("bot.py")` satisfies that requirement immediately with zero configuration — just make sure `host="0.0.0.0"` (the default) and that `port` matches whatever the platform expects (often provided via a `PORT` environment variable — read it yourself and pass it to `port=`).
* **Docker/systemd:** because `staypresent.run()` exits with a non-zero code when a bot ultimately fails to stay up (see [Crash Recovery Protocol](#crash-recovery-protocol)), your container/service's own restart policy (`restart: always`, `Restart=on-failure`, etc.) can act as a second, outer safety net beyond StayPresent's own internal restarts.
* **Free-tier inactivity spin-down:** if your host spins the service down after a period of no *inbound* traffic (as opposed to just requiring an open port), pair `staypresent.run()` with `staypresent.cron()` pinging your own public URL — see [Section 5](#5-self-ping--keep-warm-staypresentping--staypresentcron).

---

## 11. FAQ

### Is `waitress` mandatory?

No. If it isn't installed, StayPresent automatically falls back to Flask's built-in development server and logs a one-time warning. For production environments, installing the `prod` extra is recommended:

```bash
pip install staypresent[prod]

```

---

### Do I need to install anything for Markdown rendering?

No. Markdown rendering (headings, tables, emphasis, links, images, code blocks, theming, favicon/title/description support — everything in [Section 7](#7-the-built-in-markdown-renderer)) is built into StayPresent itself. No optional package is required.

---

### Can StayPresent run more than one bot at once?

Yes. Pass a list of file paths to `bot_file`:

```python
staypresent.run(["telegram_bot.py", "discord_bot.py"])
```

Each bot is supervised (and restarted on crash) independently. For per-bot arguments or environment variables, use the `bots` parameter instead — see [Section 4.1](#41-running-multiple-bots).

---

### My bot uses relative imports and fails with `ImportError: attempted relative import`. What do I do?

Use `bot_module` instead of `bot_file`. `bot_file` runs your bot the way `python bot.py` would, which breaks package-relative imports (`from . import something`) the exact same way running it directly from the command line would. `bot_module` runs it as `python -m mypkg.bot` instead:

```python
staypresent.run(bot_module="mypkg.bot")
```

See [Section 4.2](#42-bots-inside-a-package-bot_module) for the full rules, including how to mix file- and module-based bots together via `bots`.

---

### What happens if two of my bot files have the same filename?

Nothing breaks. Bots are tracked by their position in the list, not by filename, so `staypresent.run(["shard_a/bot.py", "shard_b/bot.py"])` runs both as fully independent processes with independent crash recovery. The only thing that changes is cosmetic: StayPresent detects the shared filename and automatically shows each bot's full path in the logs instead of just the filename, so crash/restart messages stay unambiguous. See [Section 4.1](#41-running-multiple-bots).

---

### What happens if I register two responses at the same path?

The most recently registered one wins — this is also how you intentionally update a response (e.g. calling `json()` again to refresh a status payload), so it never raises an error. If the response *type* at that path actually changes (e.g. it was `json` and a later call registers `text` there), StayPresent logs a `WARNING` so you can spot an unintended collision between two bots or two parts of your code. See [Section 3.7](#37-custom-paths--multiple-responses).

---

### Can I serve more than one response at different paths?

Yes. `text()`, `json()`, `html()`, `markdown()`, and `status()` all accept a `path` argument (default `"/"`):

```python
staypresent.web.json({"status": "online"})
staypresent.web.text("bot #2 status", path="/bot2")
```

See [Section 3.7](#37-custom-paths--multiple-responses) for the full rules (trailing-slash redirects, static asset resolution, etc.).

---

### How do I control light/dark mode on a rendered Markdown page?

Pass `mode="light"`, `mode="dark"`, or leave it on the default `mode="auto"` to follow the visitor's own OS/browser preference automatically:

```python
staypresent.web.markdown("guide.md", mode="dark")
```

See [Section 3.4](#34-markdown-responses) for full details.

---

### Can I set a custom favicon, title, or description for a Markdown page?

Yes, directly from Python:

```python
staypresent.web.markdown(
    "guide.md",
    favicon="favicon.png",     # or a direct URL
    title="My Docs",
    description="A short summary for link previews.",
)
```

See [Section 3.4](#34-markdown-responses) for how favicon resolution works for local files vs. direct URLs.

---

### Can I disable automatic restarts?

Yes. Set `restart_on_crash=False`. The affected bot will simply stop after its first crash, and `staypresent.run()` will still exit with a non-zero code once every bot has finished (in case others are still running).

---

### What happens if my bot crashes?

If `restart_on_crash=True` (the default), StayPresent will attempt to restart it up to `max_restarts` times, waiting `restart_delay` seconds between each attempt. If your bot stays alive for `restart_reset_after` seconds after a restart, its crash counter resets to zero. See [Crash Recovery Protocol](#crash-recovery-protocol) for the full behavior, including what happens with multiple bots.

---

### Does StayPresent interfere with my own logging setup?

No. StayPresent logs only to its own `"staypresent"` logger and never touches Python's root logger (it does not call `logging.basicConfig()`). See [Section 9](#9-logging).

---

### Is `/health` reserved? Can I override it?

It's a *default*, not a reservation. If you don't configure anything at `/health`, it returns `{"status": "ok"}`. If you do register a response there via `staypresent.web`, yours is served instead. See [Section 6](#6-built-in-defaults---health--status).

---

### Do I need to set up the status page myself?

No. A status page is served at `/status` by default the moment `staypresent.run()` starts, with no configuration at all. Call `staypresent.web.status()` yourself only if you want to change its title, theme, footer links, or admin key. See [Section 3.5](#35-status-pages-staypresentwebstatus).

---

### Who can see the status page, and what do they see?

Anyone — the page itself, its live data, and the overall up/down status are public by design, the same as a real status page. What's gated behind the optional `api_key` admin login is extra technical detail: the actual process exit code behind a crash, and a recent stdout/stderr tail per service. Without admin access, an incident still shows up with a plain-language description ("Service disruption detected — automatically recovering"), just without that detail. See [Section 3.5](#35-status-pages-staypresentwebstatus).

---

### How do I stop a bot from showing up on the status page?

Pass `status=False` to `staypresent.run()` (hides every bot that call configures), or set `"status": False` on that one bot's own entry in `bots=[...]` (overrides `run()`'s own default for just that bot). The bot is still fully supervised — crash detection and restarts are unaffected — it just doesn't get a row. See [Section 3.5](#35-status-pages-staypresentwebstatus).

---

### Can I detect a bot that's hung, not just one that crashed?

Yes, with `staypresent.heartbeat()`. Call it periodically from inside your bot's own loop, and pass `heartbeat_timeout=<seconds>` to `staypresent.run()`; a bot that goes longer than that without checking in is terminated and restarted the same way a crash would be. See [Section 4.3](#43-hang-detection-staypresentheartbeat).

---

### Can I run StayPresent with no web server at all, or a web server with no bot?

Yes to both. `staypresent.run("worker.py", web_server=False)` supervises a bot with no HTTP server. `staypresent.run()` with no `bot_file`/`bot_module`/`bots` runs the web server on its own. The only combination that's rejected is both at once, since that would do nothing. See [Section 4.4](#44-running-without-a-web-server-or-without-bots).

---

### Can I keep specific files out of a directory `html()`/`markdown()` serves?

Yes, with `exclude`:

```python
staypresent.web.html("templates/index.html", exclude=[".env", ".git", "*.py", "secrets.json"])
```

A request for anything matching an `exclude` pattern gets a plain 404, the same as if the file didn't exist. See [Section 3.3](#33-html--static-assets).