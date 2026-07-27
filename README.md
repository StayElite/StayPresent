<h1 align="center">StayPresent</h1>
<p align="center">
  <a href="https://github.com/NTDevLops/StayPresent/"><img src="https://i.ibb.co/nXKNzwf/Stay-Present-2.png" alt="StayPresent Logo" height="225"></a>
</p>
<p align="center">
  <a href="https://pypi.org/project/staypresent/"><img src="https://img.shields.io/pypi/v/staypresent.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/staypresent/"><img src="https://img.shields.io/pypi/pyversions/staypresent.svg" alt="Python versions"></a>
  <a href="https://github.com/NTDevLops/StayPresent/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
</p>
<p align="center">
  <a href="https://pypi.org/project/staypresent/"><img src="https://static.pepy.tech/personalized-badge/staypresent?period=weekly&units=INTERNATIONAL_SYSTEM&left_color=GREY&right_color=RED&left_text=downloads%2Fweek" alt="Downloads per week"></a>
  <a href="https://pypi.org/project/staypresent/"><img src="https://static.pepy.tech/personalized-badge/staypresent?period=monthly&units=INTERNATIONAL_SYSTEM&left_color=GREY&right_color=RED&left_text=downloads%2Fmonth" alt="Downloads per month"></a>
  <a href="https://pypi.org/project/staypresent/"><img src="https://static.pepy.tech/personalized-badge/staypresent?period=total&units=INTERNATIONAL_SYSTEM&left_color=GREY&right_color=RED&left_text=downloads" alt="Total downloads"></a>
</p>

### 🛖 About

A lightweight Python package designed to keep your bots and background scripts alive by running a dedicated Flask web server alongside your main application.

Perfect for deploying on platforms like **Render**, **Railway**, **Koyeb**, **Heroku**, or any host that requires an active HTTP port to keep your service running.

---

## Contents

- [Features](#-features)
- [Installation](#-installation)
- [Usage Guide](#-usage-guide)
- [Custom Paths & Multiple Responses](#-custom-paths--multiple-responses)
- [Running Multiple Bots](#-running-multiple-bots)
- [Self-Ping / Keep-Warm](#-self-ping--keep-warm)
- [API Reference](#️-api-reference)
- [Logging](#-logging)
- [Requirements](#-requirements)
- [Use Cases](#-use-cases)

---

> 📖 **Full Documentation:** For complete documentation, API reference, deployment guides, and FAQs, open [DOCUMENTATION.md](https://github.com/NTDevLops/StayPresent/blob/main/DOCUMENTATION.md).

---

## 🚀 Features

* **Zero-Friction Setup:** Get running with just one line of code.
* **Production-Ready by Default:** Automatically detects and uses `waitress` to avoid Flask's "development server" warnings.
* **Multiple Bot Support:** Run several bot processes side-by-side under one web server, each monitored and restarted independently.
* **Auto-Restarts & Crash Recovery:** Automatically respawns any bot process if it crashes, complete with customizable delays and max-restart limits (per bot).
* **Flexible Responses:** Serve custom plain text, JSON (default), full HTML templates, or Markdown files rendered to HTML with StayPresent's own built-in renderer (no extra dependency required).
* **Custom Paths, Multiple Responses:** Host more than one response at once at different paths (e.g. `/`, `/status`, `/dashboard`) — handy for multi-bot setups where each bot gets its own endpoint.
* **Static Asset Serving:** Automatically serves CSS, JS, and images located next to your HTML/Markdown files, scoped correctly even when several are hosted at different paths.
* **Advanced Control:** Easily pass custom command-line arguments and environment variables directly to your bot process(es), shared or per-bot.
* **Fail-Safe Logging:** Logs a clear error if the underlying web server dies unexpectedly.
* **Optional Self-Ping / Keep-Warm:** Periodically ping your own public URL in the background to prevent free-tier hosts from spinning your service down due to inactivity — fully opt-in, off by default.

---

## 📦 Installation

Install via pip:

```bash
pip install staypresent

```

**Recommended for Production:**
To automatically use a production WSGI server and suppress Flask development warnings, install the `prod` extra. This pulls in [`waitress`](https://pypi.org/project/waitress/).

```bash
pip install staypresent[prod]

```

*(Note: If `waitress` isn't installed, StayPresent gracefully falls back to Flask's built-in development server and logs a one-time warning.)*

Markdown rendering (`staypresent.web.markdown(...)`) works out of the box — StayPresent ships its own dependency-free Markdown-to-HTML renderer, so there's nothing extra to install for it.

---

## 💻 Usage Guide

### Basic Usage (Text Response)

```python
import staypresent

staypresent.web.text("Made With ❤️")
staypresent.run("bot.py")

```

*Navigating to `http://localhost:8080` will return plain text: `Made With ❤️*`

> **Note:** If you don't configure a response, StayPresent defaults to a JSON response of `{"message": "I'm Present"}` at the root `/` route.

### JSON Response

A safe copy of your dictionary is stored. If you need to update live data, just call `staypresent.web.json()` again.

```python
import staypresent

staypresent.web.json({
    "status": "online",
    "developer": "John",
    "message": "Made With Love ❤️"
})

staypresent.run("bot.py")

```

### HTML Response (with Static Files)

Serve a full HTML page. The file is read fresh on every request, allowing you to edit your HTML on disk without restarting your bot.

```python
import staypresent

# The path is validated immediately and will raise a FileNotFoundError if missing
staypresent.web.html("template/index.html")
staypresent.run("bot.py")

```

**Serving Static Assets:**
Any files (CSS, JS, images) in the same directory as your HTML file are automatically served. Path traversal is strictly blocked for security.

```html
<!-- template/index.html -->
<!DOCTYPE html>
<html>
  <head>
    <title>My Bot</title>
    <link rel="stylesheet" href="style.css">
  </head>
  <body>
    <h1>I'm alive!</h1>
    <img src="images/logo.png">
  </body>
</html>

```

### Markdown Response

Serve a `.md` file, rendered to HTML. Like `html()`, the file is re-read (and re-rendered) fresh on every request.

```python
import staypresent

staypresent.web.markdown("CHANGELOG.md")
staypresent.run("bot.py")

```

Rendering is handled by StayPresent's own built-in Markdown-to-HTML renderer — no extra package required. It covers headings (with anchor IDs), paragraphs, bold/italic/strikethrough, inline and fenced code blocks, links and images, blockquotes, ordered/unordered lists (including nesting), tables with column alignment, horizontal rules, and hard line breaks.

Files (like images) next to your `.md` file are served automatically, the same as with `html()`.

### Custom Host, Port, and Threads (Complete Example)

```python
import staypresent

staypresent.web.json({
    "status": "Running",
    "version": "1.0.0"
})

staypresent.run(
    "bot.py",
    host="0.0.0.0",
    port=8080,
    threads=8  # Increase if receiving real web traffic
)

```

---

## 🧭 Custom Paths & Multiple Responses

Every `staypresent.web` function (`text`, `json`, `html`, `markdown`) accepts an optional `path` argument. It defaults to `"/"`, matching the original behavior — but you can host as many independent responses as you like, each at its own path, all served by the same web server.

```python
import staypresent

staypresent.web.json({"status": "online"})                       # served at "/"
staypresent.web.text("bot #2 is alive", path="/bot2")             # served at "/bot2"
staypresent.web.html("dashboard.html", path="/dashboard")         # served at "/dashboard/"
staypresent.web.markdown("CHANGELOG.md", path="/changelog")       # served at "/changelog/"

staypresent.run("bot.py")

```

> **Note on trailing slashes:** for `html()`/`markdown()` at any path other than `"/"`, StayPresent automatically redirects `/dashboard` → `/dashboard/`. This isn't optional — it's what makes relative asset links inside your file (`<link href="style.css">`, `<img src="images/logo.png">`) resolve correctly against that file's own directory instead of its parent. `text()`/`json()` responses don't need this since they have no static assets to resolve.

A handful of small helpers make working with multiple paths easier:

```python
staypresent.web.paths()                 # -> ['/', '/bot2', '/changelog', '/dashboard']
staypresent.web.get_all()               # -> {'/': {...}, '/bot2': {...}, ...}
staypresent.web.get("/bot2")            # -> {'type': 'text', 'value': 'bot #2 is alive'}
staypresent.web.remove("/bot2")         # stop hosting a response, returns True/False

```

> **Reserved path:** `/health` is reserved for StayPresent's built-in health check endpoint (see below) and can't be overridden — attempting to `staypresent.web.text(..., path="/health")` raises a `ValueError`.

---

## 🤖 Running Multiple Bots

`staypresent.run()` can launch and independently supervise more than one bot process at once, all behind the same web server.

### Same args/env for every bot

Pass a list of file paths instead of a single one:

```python
import staypresent

staypresent.run(["telegram_bot.py", "discord_bot.py"])

```

Each bot is monitored and restarted on its own — one crashing (and getting restarted, per `max_restarts`/`restart_delay`) has no effect on the others. `bot_args` and `env`, if provided, are applied identically to every bot in the list.

### Per-bot args/env

For finer control, use the `bots` argument instead — a list of dicts, one per bot:

```python
import staypresent

staypresent.web.json({"status": "online"})

staypresent.run(bots=[
    {"file": "telegram_bot.py", "args": ["--verbose"]},
    {"file": "discord_bot.py", "env": {"SHARD": "0"}},
    {"file": "worker.py"},
])

```

`bots` is mutually exclusive with `bot_file`/`bot_args`/`env` — pick whichever style fits: `bot_file` (+ optional shared `bot_args`/`env`) for the simple case, `bots` when each process needs its own arguments or environment.

### How failures are handled with multiple bots

* Each bot has its own independent restart counter, so `max_restarts` is a *per-bot* budget.
* `staypresent.run()` waits for every bot to finish before returning or exiting — it doesn't stop supervising the others just because one of them gave up.
* If **any** bot ultimately fails to stay up (restarts exhausted, or `restart_on_crash=False` and it crashed), `staypresent.run()` exits the whole process with a non-zero exit code once every bot has finished, the same fail-loud behavior as the single-bot case.
* `Ctrl+C` / `SIGTERM` stops the web server and **all** bot processes cleanly.

---

## 📡 Self-Ping / Keep-Warm

Some free hosting tiers (Render, Railway, Replit, etc.) spin your service down after a period of inactivity, and only wake it back up on the next incoming request. `staypresent.ping()` and `staypresent.cron()` are a completely optional way to work around this by having your app periodically hit its own **public** URL — nothing runs unless you call one of them yourself.

> ⚠️ **Ping your public URL, not `127.0.0.1`/`0.0.0.0`.** Traffic that never leaves the machine doesn't count as activity to the hosting platform. `staypresent.cron("https://your-app.onrender.com")` works for that; `staypresent.cron("0.0.0.0", port=8080)` is only useful for locally smoke-testing that your own server is responding.

### `staypresent.ping(...)` — one-off check

Synchronous — fires a single HTTP GET and returns immediately with the result.

```python
result = staypresent.ping("https://my-app.onrender.com")
# -> {"url": "...", "ok": True, "status_code": 200, "elapsed": 0.31, "error": None}

if not result["ok"]:
    print("Something's wrong:", result["error"])
```

### `staypresent.cron(...)` — repeat on a schedule

Non-blocking — starts a background thread that calls `ping()` on a schedule. Call it before `staypresent.run()`.

```python
import staypresent

# Ping our own public URL every 4 minutes to keep the free-tier instance awake
staypresent.cron("https://my-app.onrender.com", interval=240)

staypresent.run("bot.py")
```

With callbacks, e.g. to log failures somewhere more visible:

```python
staypresent.cron(
    "https://my-app.onrender.com",
    interval=240,
    on_success=lambda r: print(f"warm ping ok ({r['elapsed']}s)"),
    on_failure=lambda r: print(f"warm ping failed: {r['error']}"),
)
```

`host` accepts a bare domain (`"my-app.onrender.com"`), a full URL (`"https://my-app.onrender.com/health"`), or a local bind address (`"0.0.0.0"`, treated as `127.0.0.1`) — same rules for both `ping()` and `cron()`.

`cron()` returns a handle if you ever need to cancel it:

```python
handle = staypresent.cron("https://my-app.onrender.com", interval=240)
...
handle.stop()          # stop pinging
handle.is_running       # True/False
```

Starting and stopping are both logged (`Started cron: pinging ... every 240s`), so you can confirm it's actually active. Pings run one at a time — if a ping takes a while to time out, the actual gap before the next one grows accordingly rather than piling up requests in parallel.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `host` | `str` | **Required** | Bare domain, full URL, or bind address (see above). |
| `port` | `int` | `None` | Port to connect to. Ignored if `host` is already a full URL. |
| `path` | `str` | `"/"` | Path to request. Ignored if `host` is already a full URL. |
| `timeout` | `float` | `10.0` | Seconds to wait for a response before treating the ping as failed. |
| `https` | `bool` | `None` | Force `http`/`https`. Auto-detected by default (local addresses → `http`, everything else → `https`). |
| `interval` *(cron only)* | `float` | `300.0` | Seconds between pings. |
| `repeat` *(cron only)* | `bool` | `True` | Keep pinging forever, or just once in the background. |
| `on_success` *(cron only)* | `callable` | `None` | `fn(result)` called after each successful ping. |
| `on_failure` *(cron only)* | `callable` | `None` | `fn(result)` called after each failed ping. |

---

### `staypresent.run(...)`

Launch your bot script(s) alongside the web server.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `bot_file` | `str` or `list[str]` | `None` | Path to the Python script to run, or a list of paths to run several bots at once. Mutually exclusive with `bots`. |
| `host` | `str` | `"0.0.0.0"` | Host to bind the web server to. |
| `port` | `int` | `8080` | Port to bind the web server to. |
| `production` | `bool` | `True` | Uses `waitress` if installed. Set to `False` to force the Flask dev server. |
| `threads` | `int` | `4` | Number of worker threads for `waitress`. Increase this if serving real web traffic rather than just keep-alive pings. *(Requires `production=True` and `waitress`)*. |
| `restart_on_crash` | `bool` | `True` | Relaunch a bot process if it exits with a non-zero exit code. |
| `max_restarts` | `int` | `5` | Maximum restart attempts per bot after a crash before giving up. |
| `restart_delay` | `float` | `2.0` | Seconds to wait before relaunching a bot process after a crash. |
| `restart_reset_after` | `float` | `60.0` | Seconds a bot must stay alive to reset its consecutive crash counter back to 0. |
| `bot_args` | `list` | `None` | Extra command-line arguments passed to every bot in `bot_file` (e.g., `["--verbose"]`). Must be a list — a bare string like `"--flag"` raises a clear error instead of silently exploding into individual characters. Ignored when `bots` is used. |
| `env` | `dict` | `None` | Extra environment variables for every bot in `bot_file`. Merges over the current environment. Ignored when `bots` is used. |
| `bots` | `list[dict]` | `None` | Per-bot configuration: `[{"file": "bot.py", "args": [...], "env": {...}}, ...]` (`args`/`env` optional per entry). Mutually exclusive with `bot_file`/`bot_args`/`env` — see [Running Multiple Bots](#-running-multiple-bots). |

> **Note:** `port`, `threads`, `max_restarts`, `restart_delay`, and `restart_reset_after` are validated up front — passing an invalid value (e.g. `threads=0`, a negative `port`) raises a `ValueError` immediately instead of failing silently or deep inside `waitress`. Likewise, every bot file (in `bot_file` or `bots`) is checked to exist *before* the server starts.

### Crash Recovery Details

StayPresent automatically monitors every bot process. If one exits with a non-zero exit code, StayPresent restarts it based on your configuration:

* **Clean Exits:** An exit code of `0` is considered intentional and will *not* trigger a restart.
* **Independent Supervision:** With multiple bots, each one is monitored and restarted completely independently — one crashing (or exhausting its restarts) doesn't pause or stop the others.
* **Manual Shutdowns:** Stopping StayPresent via `Ctrl+C` (SIGINT) or `SIGTERM` shuts down the server and *every* bot process cleanly.
* **Smart Counters:** The `max_restarts` limit applies to *consecutive* crashes, per bot. If a bot runs successfully for the duration of `restart_reset_after` (default 60 seconds), its crash counter resets.
* **Non-Zero Exit on Giving Up:** `staypresent.run()` waits for every bot to finish. If any bot ultimately failed to stay up — restarts disabled and it crashed, or `max_restarts` was exhausted for it — `staypresent.run()` then exits the whole process with a non-zero exit code instead of returning normally. This lets a hosting platform's own restart-on-crash policy (Render, Railway, Docker, systemd, etc.) kick in as a last resort, instead of the process quietly exiting `0` as if nothing went wrong.

### Built-in Health Check

A dedicated `/health` endpoint is automatically exposed, returning `{"status": "ok"}`. This is incredibly useful for platform pingers and uptime monitors that require a dedicated health-check path separate from your regular response(s). Because it's built in, `/health` is a reserved path — you can't register your own response there.

### `staypresent.web` Reference

| Function | Description |
| --- | --- |
| `text(message, path="/")` | Serve plain text at `path`. |
| `json(data, path="/")` | Serve a JSON-serializable dict/list at `path`. A deep copy is stored. |
| `html(file_path, path="/")` | Serve an HTML file (read fresh every request) at `path`, plus its neighboring static assets. |
| `markdown(file_path, path="/")` | Serve a Markdown file, rendered to HTML (read + re-rendered fresh every request) at `path`, plus its neighboring static assets. |
| `remove(path="/")` | Stop hosting a response at `path`. Returns `True`/`False`. |
| `get(path="/")` | Returns `{"type": ..., "value": ...}` for `path`, or `{}` if nothing is registered there. |
| `get_all()` | Returns every registered path and its state as a single dict. |
| `paths()` | Returns a sorted list of every currently-registered path. |

### Inspecting the Current Response

```python
staypresent.web.get()
# -> {"type": "json", "value": {"message": "I'm Present"}}
```

Returns whatever was last configured for `path` (default `"/"`) via `text()` / `json()` / `html()` / `markdown()`, as `{"type": ..., "value": ...}`. Mainly useful for debugging or unit-testing your own code around StayPresent.

---

## 📝 Logging

StayPresent logs to its own `"staypresent"` logger, not the root logger — it never calls `logging.basicConfig()` globally. This means it won't clobber, duplicate, or reformat logging you've already set up elsewhere in your script for unrelated loggers.

To change the log level or format, configure it like any other logger:

```python
import logging
logging.getLogger("staypresent").setLevel(logging.WARNING)
```

---

## 🛠 Requirements

* Python 3.8+
* Flask
* `waitress` *(optional, but highly recommended for production — `pip install staypresent[prod]`)*

Markdown rendering has no extra dependency — StayPresent renders it itself.

## 💡 Use Cases

* Discord & Telegram Bots
* Background Workers & Automation Scripts
* Keeping deployments alive on Render, Railway, Koyeb, and Heroku

---

**License:** MIT License

*Made with ❤️ using Python.*