# StayPresent Documentation

**StayPresent** is a lightweight Python package designed to manage the lifecycle of background scripts and bot applications. It runs a Flask-powered HTTP server alongside your application, with optional production serving through Waitress, making it easy to deploy services on platforms that require an active HTTP port (e.g., Render, Railway, Koyeb, Heroku).

---

## 1. Requirements

* **Python** 3.8+
* **Flask**
* **waitress** (optional, but highly recommended for production)

Markdown rendering (`staypresent.web.markdown(...)`) needs no extra package — StayPresent ships its own dependency-free Markdown-to-HTML renderer.

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

**Markdown Rendering:**

Works out of the box — StayPresent renders `.md` responses to HTML with its own built-in renderer, so there's no extra package to install.

---

## 3. Web Server Configuration (`staypresent.web`)

The `staypresent.web` module dictates the HTTP response(s) served by the background web server. Every function accepts an optional `path` argument (default `"/"`), so you can host multiple independent responses at once — see [Section 3.5](#35-custom-paths--multiple-responses) below. If the root path (`"/"`) is left unconfigured, it defaults to a JSON response: `{"message": "I'm Present"}`.

**Basic Usage Example:**

```python
import staypresent

staypresent.web.json({
    "status": "running"
})

staypresent.run("bot.py")

```

### Text Responses

Returns a `text/plain` response.

```python
import staypresent

staypresent.web.text("Service Operational")

```

### JSON Responses

Returns an `application/json` response. The dictionary is safely copied. Subsequent calls will update the live response data.

```python
import staypresent

staypresent.web.json({
    "status": "online",
    "version": "1.2.0"
})

```

### HTML & Static Assets

Reads and serves an HTML file on every request. This allows for dynamic, on-disk updates without restarting the Python process.

```python
import staypresent

staypresent.web.html("templates/index.html")

```

> **Note:** Any static assets (CSS, JS, images) located in the same directory as the target HTML file are automatically served. Path traversal is strictly prohibited by internal security checks.

### Markdown Responses

Reads a `.md` file and renders it to HTML on every request, the same on-disk-editable model as `html()`.

```python
import staypresent

staypresent.web.markdown("CHANGELOG.md")

```

Rendering is done by StayPresent's own built-in, dependency-free Markdown-to-HTML renderer — nothing extra to install. It covers headings (with auto-generated anchor IDs), paragraphs, bold/italic/strikethrough, inline and fenced code blocks, links and images, blockquotes, ordered/unordered lists (including nesting), tables with column alignment, horizontal rules, and hard line breaks. Static assets next to the `.md` file (e.g. images) are served automatically, exactly as with `html()`.

### 3.5 Custom Paths & Multiple Responses

`text()`, `json()`, `html()`, and `markdown()` all accept a `path` keyword argument. This lets a single StayPresent instance host several independent responses at once — useful for giving each of multiple bots (see Section 4.1) its own status endpoint.

```python
import staypresent

staypresent.web.json({"status": "online"}, path="/")
staypresent.web.text("bot #2 is alive", path="/bot2")
staypresent.web.html("dashboard.html", path="/dashboard")
staypresent.web.markdown("CHANGELOG.md", path="/changelog")

```

**Path rules:**

* A path is normalized: it must start with `/`, repeated slashes are collapsed, and a trailing slash is stripped (`"/status/"` and `"/status"` refer to the same route).
* Paths must not contain `?` or `#` — StayPresent raises `ValueError` if they do, since those characters belong in a query string/fragment, not a route.
* `/health` is reserved for the built-in health check (Section 6) and cannot be registered via `staypresent.web`.
* For `html()`/`markdown()` at any path other than `"/"`, a bare request to that path (e.g. `/dashboard`) is automatically redirected (HTTP 308) to a trailing-slash version (`/dashboard/`). This is required for relative asset links inside the file (`href="style.css"`, `src="images/logo.png"`) to resolve against that file's own directory rather than its parent. `text()`/`json()` responses don't need this, since they have no static assets to resolve.
* Static asset lookups use the *longest matching path prefix* across every registered `html()`/`markdown()` route, so nested/overlapping mounts (e.g. `"/"` and `"/dashboard"` both hosting HTML) resolve unambiguously to the right directory.

**Managing registered paths:**

```python
staypresent.web.paths()          # -> ['/', '/bot2', '/changelog', '/dashboard']
staypresent.web.get_all()        # -> {'/': {'type': 'json', 'value': {...}}, '/bot2': {...}, ...}
staypresent.web.get("/bot2")     # -> {'type': 'text', 'value': 'bot #2 is alive'}
staypresent.web.remove("/bot2")  # -> True (was registered) / False (wasn't)

```

### State Inspection

To retrieve the currently configured response payload for debugging or testing:

```python
current_state = staypresent.web.get()
# Returns: {"type": "json", "value": {"status": "online", ...}}

```

`get()` defaults to `path="/"`; pass a different `path` to inspect any other registered route.

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
* Each bot gets its own restart counter and is monitored on its own thread — a crash (and subsequent restart) in one bot has no effect on the others.
* `staypresent.run()` waits for every bot to finish (or fail permanently) before returning or exiting the process.
* `Ctrl+C`/`SIGTERM` terminates the web server and *all* bot processes.

### Execution Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `bot_file` | `str` or `list[str]` | `None` | Target Python script(s) to execute concurrently. Mutually exclusive with `bots`. |
| `host` | `str` | `"0.0.0.0"` | Network interface to bind the web server. |
| `port` | `int` | `8080` | Port allocation for the web server. |
| `production` | `bool` | `True` | Utilizes `waitress` if available. Set to `False` to force Flask's dev server. |
| `threads` | `int` | `4` | Worker threads for `waitress` (requires `production=True`). |
| `restart_on_crash` | `bool` | `True` | Relaunches a bot upon a non-zero exit code. |
| `max_restarts` | `int` | `5` | Maximum consecutive restart attempts, per bot. |
| `restart_delay` | `float` | `2.0` | Seconds to wait before process respawn. |
| `restart_reset_after` | `float` | `60.0` | Seconds of continuous uptime required to reset a bot's crash counter to zero. |
| `bot_args` | `list` | `None` | CLI arguments to pass to every bot in `bot_file` (e.g., `["--verbose"]`). Ignored when `bots` is used. |
| `env` | `dict` | `None` | Environment variables injected into every bot in `bot_file`. Ignored when `bots` is used. |
| `bots` | `list[dict]` | `None` | Per-bot configuration: `[{"file": ..., "args": [...], "env": {...}}, ...]`. Mutually exclusive with `bot_file`/`bot_args`/`env`. |

### Crash Recovery Protocol

StayPresent strictly monitors every bot's subprocess lifecycle, independently:

* **Clean Exits:** An exit code of `0` is treated as an intentional shutdown for that bot and bypasses restart logic.
* **Signals:** Interruptions (`SIGINT`/`Ctrl+C`, `SIGTERM`) initiate a clean teardown of the server and every bot.
* **Terminal Failures:** If `max_restarts` is exhausted for a bot, or if restarts are disabled and it crashes, that bot is marked as permanently failed (but other bots keep running). Once every bot has finished, if any bot ended in a permanently-failed state, `staypresent.run()` exits the main process with a non-zero exit code. This ensures platform-level orchestrators (Docker, systemd) correctly interpret the failure state.

---

## 5. Keep-Warm Module (`staypresent.ping` and `staypresent.cron`)

Many platform-as-a-service (PaaS) providers hibernate instances after periods of inactivity. The Keep-Warm module provides an internal mechanism to generate synthetic traffic against your application's public URL.

> **Crucial Setup:** You must target your application's **publicly routable URL**. Pinging `0.0.0.0` or `127.0.0.1` will not prevent platform hibernation.

> **Note:** Keep-Warm only generates HTTP activity. It does not prevent platform policies that explicitly suspend or terminate applications (such as hard usage limits or strict free-tier quotas).

### Synchronous Pings (`staypresent.ping`)

Executes an immediate, blocking HTTP GET request.

```python
result = staypresent.ping("https://api.yourdomain.com")

```

### Scheduled Pings (`staypresent.cron`)

Spawns an isolated background thread to execute periodic requests. This must be invoked prior to `staypresent.run()`.

```python
import staypresent

# Ping the public endpoint every 4 minutes
staypresent.cron("https://api.yourdomain.com", interval=240.0)

staypresent.run("bot.py")

```

### Cron Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `host` | `str` | **Required** | Target domain, full URL, or bind address. |
| `port` | `int` | `None` | Target port. Ignored if a full URL is provided. |
| `path` | `str` | `"/"` | Target endpoint path. Ignored if a full URL is provided. |
| `timeout` | `float` | `10.0` | HTTP timeout threshold in seconds. |
| `https` | `bool` | `None` | Forces protocol. Auto-detected if unassigned. |
| `interval` *(cron only)* | `float` | `300.0` | Frequency of requests in seconds. |
| `repeat` *(cron only)* | `bool` | `True` | Dictates continuous execution vs. a single background execution. |
| `on_success` *(cron only)* | `callable` | `None` | Callback function invoked post-successful ping. |
| `on_failure` *(cron only)* | `callable` | `None` | Callback function invoked upon request timeout or failure. |

---

## 6. Observability and Health

### Built-In Health Check

StayPresent automatically provisions a dedicated `/health` endpoint. This returns a fixed `{"status": "ok"}` payload, providing a clean separation between your configured root response and internal platform uptime monitoring.

### Logging Configuration

StayPresent isolates its telemetry within a dedicated `"staypresent"` logger. It will not mutate the root logger or interfere with existing logging configurations within your application.

To adjust verbosity:

```python
import logging
logging.getLogger("staypresent").setLevel(logging.INFO)

```

---

## 7. API Reference

### `staypresent.web`

* **`web.text(message: str, path: str = "/")`** – Configures `path` to return plain text.
* **`web.json(data: Any, path: str = "/")`** – Configures `path` to return a JSON payload (deep-copied).
* **`web.html(file_path: str, path: str = "/")`** – Configures `path` to serve an HTML file, read fresh every request, alongside neighboring static files.
* **`web.markdown(file_path: str, path: str = "/")`** – Configures `path` to serve a Markdown file rendered to HTML, read and re-rendered fresh every request, alongside neighboring static files.
* **`web.remove(path: str = "/")`** – Stops hosting a response at `path`. Returns `True`/`False`.
* **`web.get(path: str = "/")`** – Returns the currently configured response state for `path` as a dictionary, or `{}` if nothing is registered there.
* **`web.get_all()`** – Returns every registered path and its state as one dictionary.
* **`web.paths()`** – Returns a sorted list of every currently-registered path.

### `staypresent`

* **`run(bot_file: str | list[str] = None, ..., bots: list[dict] = None)`** – Starts the HTTP server and manages the lifecycle of one or more bot processes.
* **`ping(host: str, ...)`** – Sends a synchronous HTTP request.
* **`cron(host: str, ...)`** – Runs scheduled background keep-warm requests.

---

## 8. Deployment Examples

StayPresent is built specifically to seamlessly handle port-binding requirements on modern PaaS environments. Ensure your `main.py` (or equivalent entry point) utilizes `staypresent.run()`.

### Render

Render assigns the listening port through the `PORT` environment variable. Configure your application to use that value when available.

```python
import os
import staypresent

staypresent.run(
    "bot.py",
    port=int(os.getenv("PORT", 8080))
)

```

**Start Command:**

```bash
python main.py

```

### Railway

Railway automatically detects Python applications and assigns a `$PORT`. The execution logic is identical to Render.

```python
import os
import staypresent

staypresent.run(
    "bot.py",
    port=int(os.getenv("PORT", 8080))
)

```

**Start Command:**

```bash
python main.py

```

---

## 9. Frequently Asked Questions (FAQ)

### Does StayPresent replace Flask?

No. StayPresent does not replace Flask. It provides a simplified wrapper around Flask-based hosting requirements for background scripts and bots, handling HTTP server setup, process management, and production WSGI configuration out of the box.

---

### Does StayPresent host my application?

No. StayPresent does not provide hosting infrastructure. It manages the local web server and application lifecycle **inside** your existing hosting environment. You still need to deploy your project on platforms like Render, Railway, Koyeb, Heroku, a VPS, or Docker.

---

### Why do I need StayPresent if my bot already works locally?

Many cloud hosting platforms require applications to listen on an HTTP port to verify health. Background bots and workers usually do not expose a web server, causing platforms to declare them unhealthy and shut them down. StayPresent solves this by running a lightweight HTTP server alongside your bot.

---

### Can StayPresent run Discord bots, Telegram bots, or automation scripts?

Yes. StayPresent is designed for long-running Python processes such as:

* Discord bots
* Telegram bots
* Web scrapers
* Automation workers
* Background jobs
* Scheduled scripts
* API polling services

---

### Does StayPresent keep my application online forever?

No. StayPresent can generate optional keep-warm HTTP requests via `cron()`, but it cannot bypass hosting provider limitations, account restrictions, resource quotas, or forced shutdown policies. Final availability always depends on your hosting provider.

---

### Does `staypresent.cron()` work with `localhost`?

No. Keep-warm requests must target your application's **public URL**.

```python
# ✅ Correct:
staypresent.cron(
    "https://my-app.onrender.com",
    interval=240
)

# ❌ Incorrect:
staypresent.cron(
    "http://127.0.0.1:8080",
    interval=240
)

```

Requests sent to `127.0.0.1` or `localhost` do not generate external inbound traffic and will not reset platform inactivity sleep timers.

---

### Is Waitress required?

No. Waitress is optional. If installed, StayPresent automatically uses Waitress as a production-grade WSGI server. Otherwise, it safely falls back to Flask's built-in development server.

For production environments, installing the `prod` extra is recommended:

```bash
pip install staypresent[prod]

```

Markdown rendering (`staypresent.web.markdown()`) needs no extra package at all — StayPresent renders `.md` files to proper HTML itself, out of the box.

---

### What happens if my bot crashes?

By default, StayPresent monitors your bot subprocess and attempts automatic recovery.

Features include:

* Automatic restarts upon non-zero exit codes
* Configurable restart limits (`max_restarts`)
* Custom restart delays (`restart_delay`)
* Automatic crash counter resets after sustained uptime (`restart_reset_after`)

```python
staypresent.run(
    "bot.py",
    restart_on_crash=True,
    max_restarts=5
)

```

---

### Can StayPresent run more than one bot at once?

Yes. Pass a list of file paths to `bot_file`:

```python
staypresent.run(["telegram_bot.py", "discord_bot.py"])
```

Each bot is supervised (and restarted on crash) independently. For per-bot arguments or environment variables, use the `bots` parameter instead — see [Section 4.1](#41-running-multiple-bots).

---

### Can I serve more than one response at different paths?

Yes. `text()`, `json()`, `html()`, and `markdown()` all accept a `path` argument (default `"/"`):

```python
staypresent.web.json({"status": "online"})
staypresent.web.text("bot #2 status", path="/bot2")
```

See [Section 3.5](#35-custom-paths--multiple-responses) for the full rules (trailing-slash redirects, static asset resolution, the reserved `/health` path, etc.).

---

### Can StayPresent render Markdown files?

Yes, via `staypresent.web.markdown("file.md")`. It renders to HTML using StayPresent's own built-in Markdown renderer — no extra package required.

---

### Can I disable automatic restarts?

Yes. Set `restart_on_crash=False`. When disabled, any subprocess crash will cause StayPresent to exit immediately with the bot's original exit code.

```python
staypresent.run(
    "bot.py",
    restart_on_crash=False
)

```

---

### Does StayPresent affect my existing logging system?

No. StayPresent isolates all of its logging under a dedicated logger namespace:

```python
import logging
logging.getLogger("staypresent")

```

It does not modify root logger handlers or invoke `logging.basicConfig()`.

---

### Can I serve my own website or dashboard with StayPresent?

Yes. StayPresent supports serving plain text, JSON payloads, static HTML templates, and associated static assets (CSS, JS, images).

```python
staypresent.web.html("templates/dashboard.html")

```

---

### Is StayPresent production ready?

Yes. StayPresent is designed specifically for production deployment scenarios where background processes require HTTP health endpoints, process supervision, crash recovery, and WSGI serving. However, overall reliability still depends on application code quality and hosting provider limits.

---

### Does StayPresent support Docker?

Yes. StayPresent works inside Docker containers like any standard Python package.

```dockerfile
CMD ["python", "main.py"]

```

Your `main.py` entry point can use `staypresent.run()` to expose the required HTTP port while managing the background worker process.

---

### What Python versions are supported?

StayPresent supports Python 3.8 and newer:

* Python 3.8
* Python 3.9
* Python 3.10
* Python 3.11
* Python 3.12+

---

### Is StayPresent free to use?

Yes. StayPresent is open-source software released under the **MIT License**. It can be freely used, modified, and distributed in both personal and commercial projects.

---

## 10. License

StayPresent is released under the **MIT License**.