<h1 align="center">StayPresent</h1>
<p align="center">
  <a href="https://github.com/StayElite/StayPresent/"><img src="https://i.ibb.co/nXKNzwf/Stay-Present-2.png" alt="StayPresent Logo" height="225"></a>
</p>
<p align="center">
  <a href="https://pypi.org/project/staypresent/"><img src="https://img.shields.io/pypi/v/staypresent.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/staypresent/"><img src="https://img.shields.io/pypi/pyversions/staypresent.svg" alt="Python versions"></a>
  <a href="https://github.com/StayElite/StayPresent/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT"></a>
</p>
<p align="center">
  <a href="https://pypi.org/project/staypresent/"><img src="https://static.pepy.tech/personalized-badge/staypresent?period=weekly&units=INTERNATIONAL_SYSTEM&left_color=GREY&right_color=RED&left_text=downloads%2Fweek" alt="Downloads per week"></a>
  <a href="https://pypi.org/project/staypresent/"><img src="https://static.pepy.tech/personalized-badge/staypresent?period=monthly&units=INTERNATIONAL_SYSTEM&left_color=GREY&right_color=RED&left_text=downloads%2Fmonth" alt="Downloads per month"></a>
  <a href="https://pypi.org/project/staypresent/"><img src="https://static.pepy.tech/personalized-badge/staypresent?period=total&units=INTERNATIONAL_SYSTEM&left_color=GREY&right_color=RED&left_text=downloads" alt="Total downloads"></a>
</p>

### 🛖 About

A lightweight Python package designed to keep your bots and background scripts alive by running a dedicated Flask web server alongside your main application(s).

Perfect for deploying on platforms like **Render**, **Railway**, **Koyeb**, **Heroku**, or any host that requires an active HTTP port to keep your service running.

---

## Contents

- [Features](#-features)
- [Installation](#-installation)
- [Quickstart](#-quickstart)
- [Usage Guide](#-usage-guide)
  - [Text Response](#text-response)
  - [JSON Response](#json-response)
  - [HTML Response](#html-response)
  - [Markdown Response](#markdown-response)
  - [Custom Host, Port, and Threads](#custom-host-port-and-threads-complete-example)
- [Custom Paths & Multiple Responses](#-custom-paths--multiple-responses)
- [Running Multiple Bots](#-running-multiple-bots)
- [Self-Ping / Keep-Warm](#-self-ping--keep-warm)
- [API Reference](#️-api-reference)
- [Logging](#-logging)
- [Requirements](#-requirements)
- [Use Cases](#-use-cases)

---

> 📖 **Full Documentation:** For complete documentation, API reference, deployment guides, and FAQs, open [DOCUMENTATION.md](https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.md).

## ✨ Features

* **Zero-Friction Setup:** Get running with just one line of code.
* **Production-Ready by Default:** Automatically detects and uses `waitress` to avoid Flask's "development server" warnings.
* **Multiple Bot Support:** Run several bot processes side-by-side under one web server, each monitored and restarted independently, with shared or per-bot arguments/environment variables.
* **Package-Aware Bot Launching:** Bots that live inside a package and rely on relative imports can be launched as a proper module (`python -m mypkg.bot`) via `bot_module`, instead of failing the way a bare `python bot.py` would.
* **Auto-Restarts & Crash Recovery:** Automatically respawns any bot process if it crashes, complete with customizable delays and consecutive-crash budgets — per bot.
* **Flexible Responses:** Serve custom plain text, JSON (default), full HTML templates, or beautifully rendered Markdown.
* **Built-in Markdown Renderer — Zero Extra Dependencies:** Headings, emphasis, strikethrough, links, images, autolinks, nested lists, nested blockquotes, tables, fenced/indented code blocks, raw HTML passthrough, and a GitHub-flavored stylesheet — no `markdown` package required.
* **Light / Dark / Auto Theming:** Every Markdown page can be forced to `light` or `dark`, or left on `auto` (default) to automatically follow the visitor's own OS/browser preference.
* **Page Metadata for Markdown Pages:** Set a custom favicon, `<title>`, and meta/Open Graph description directly from Python — no template editing needed.
* **Custom Paths, Multiple Responses:** Host more than one response at once at different paths (e.g. `/`, `/status`, `/dashboard`) — handy for multi-bot setups where each bot gets its own endpoint.
* **Static Asset Serving:** Automatically serves CSS, JS, images, and favicons located next to your HTML/Markdown files, scoped correctly even when several are hosted at different paths.
* **Advanced Process Control:** Easily pass custom command-line arguments and environment variables directly to your bot process(es), shared across all of them or configured individually per bot.
* **Fail-Safe Logging:** Logs a clear, dedicated error if the underlying web server dies unexpectedly, and never touches Python's root logger.
* **Optional Self-Ping / Keep-Warm:** Periodically ping your own public URL in the background to prevent free-tier hosts from spinning your service down due to inactivity — fully opt-in, off by default.

---

## 📦 Installation

**Standard Installation:**

```bash
pip install staypresent

```

**Production Installation (Recommended):**

To suppress Flask's development-server warning and use a production-grade WSGI server, install the `prod` extra. This automatically provisions [`waitress`](https://pypi.org/project/waitress/).

```bash
pip install staypresent[prod]

```

*(Note: If `waitress` isn't installed, StayPresent gracefully falls back to Flask's built-in development server and logs a one-time warning. Nothing else is required — Markdown rendering, tables, theming, and everything else described below works out of the box with no additional packages.)*

---

## 🚀 Quickstart

```python
import staypresent

staypresent.run("bot.py")

```

That's it. This starts a background web server (defaulting to `0.0.0.0:8080`, serving `{"message": "I'm Present"}` at `/`) and runs `bot.py` alongside it, automatically restarting it if it ever crashes.

---

## 📘 Usage Guide

By default, if you don't configure anything via `staypresent.web`, the root path (`/`) returns a JSON response: `{"message": "I'm Present"}`. Every function below accepts an optional `path` argument to host more than one response at once — see [Custom Paths & Multiple Responses](#-custom-paths--multiple-responses).

### Text Response

```python
import staypresent

staypresent.web.text("Service is Online")
staypresent.run("bot.py")

```

### JSON Response

```python
import staypresent

staypresent.web.json({
    "status": "online",
    "uptime": "24h"
})
staypresent.run("bot.py")

```

### HTML Response

Serve a full HTML file. Any CSS/JS/images referenced next to it are served automatically.

```python
import staypresent

staypresent.web.html("template/index.html")
staypresent.run("bot.py")

```

### Markdown Response

Serve a `.md` file, rendered to clean, styled HTML — headings, emphasis, links, images, lists, blockquotes, tables, and fenced code blocks are all supported out of the box, with **no extra dependency required**. The file is re-read (and re-rendered) fresh on every request, so editing it on disk shows up immediately.

```python
import staypresent

staypresent.web.markdown("CHANGELOG.md")
staypresent.run("bot.py")

```

The rendered page uses a GitHub-flavored stylesheet and automatically matches the visitor's light/dark preference. You can also customize the theme and page metadata:

```python
import staypresent

staypresent.web.markdown(
    "docs/guide.md",
    path="/docs",
    mode="dark",                              # "light", "dark", or "auto" (default)
    favicon="favicon.png",                    # a file next to guide.md, or a direct URL
    title="Project Docs",                     # page <title> + Open Graph title
    description="Everything you need to get started.",  # meta + Open Graph description
)
staypresent.run("bot.py")

```

| Parameter | Default | Description |
| --- | --- | --- |
| `mode` | `"auto"` | `"auto"` follows the visitor's OS/browser color-scheme preference automatically. `"light"`/`"dark"` force that scheme for every visitor regardless of their own setting. |
| `favicon` | `None` | A direct URL (`http://`, `https://`, or `//...`) is used as-is. Anything else (e.g. `"favicon.png"`) is treated as a file next to your Markdown file — the same way neighboring CSS/images already are — and must exist there to be served correctly. |
| `title` | `None` | Sets the page `<title>` and Open Graph title. Defaults to the Markdown file's own filename when omitted. |
| `description` | `None` | Adds a `<meta name="description">` tag and an Open Graph description tag — useful for link-preview cards when the URL is shared on social media/chat apps. |

Files (images, etc.) next to your `.md` file are served automatically, exactly the same as with `html()`.

### Custom Host, Port, and Threads (Complete Example)

```python
import staypresent

staypresent.web.json({"status": "running"})

staypresent.run(
    "bot.py",
    host="0.0.0.0",
    port=5000,
    threads=8
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

> **Note on trailing slashes:** for `html()`/`markdown()` at any path other than `"/"`, StayPresent automatically redirects `/dashboard` → `/dashboard/`. This isn't optional — it's what makes relative asset links inside your file (`<link href="style.css">`, `<img src="images/logo.png">`, a relative `favicon`) resolve correctly against that file's own directory instead of its parent. `text()`/`json()` responses don't need this since they have no static assets to resolve.

A handful of small helpers make working with multiple paths easier:

```python
staypresent.web.paths()                 # -> ['/', '/bot2', '/changelog', '/dashboard']
staypresent.web.get_all()               # -> {'/': {...}, '/bot2': {...}, ...}
staypresent.web.get("/bot2")            # -> {'type': 'text', 'value': 'bot #2 is alive'}
staypresent.web.remove("/bot2")         # stop hosting a response, returns True/False

```

> **Note on `/health`:** StayPresent has a built-in default at `/health` returning `{"status": "ok"}` (see [Built-in Health Check](#built-in-health-check) below). It's a default, not a reservation — if you register your own response at `/health` via `staypresent.web`, yours is served instead.

> **Note on registering the same path twice:** calling `text()`/`json()`/`html()`/`markdown()` again for a path you've already registered is a normal way to update it (e.g. calling `json()` repeatedly to refresh a status payload) — the newest call always wins, silently. But if the response *type* at a path changes (e.g. it was `json` and a later call registers `text` there instead), that's usually a sign two different bots — or two different parts of your code — didn't realize they were both claiming the same path, so StayPresent logs a one-line warning to make that visible instead of just quietly serving whichever one happened to run last.

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

> **Note on bots with the same filename:** if two bot files share a filename (e.g. `shard_a/bot.py` and `shard_b/bot.py`), they run as fully independent processes with no conflict — StayPresent tracks each by its position in the list, not its name. The only thing that changes is the log labels: instead of two ambiguous `bot[0] 'bot.py'`/`bot[1] 'bot.py'` lines, StayPresent automatically switches to showing each one's full path (e.g. `bot[0] 'shard_a/bot.py'`) whenever a filename collision is detected, so crash/restart logs always tell them apart.

### Bots that live inside a package (`bot_module`)

If your bot isn't a standalone script — it's a module inside a package that uses package-relative imports (`from . import something`) — running it via `bot_file` fails exactly the way `python bot.py` would from the command line:

```
ImportError: attempted relative import with no known parent package
```

Use `bot_module` instead, which launches it as `python -m <module>` (exactly like running it yourself from the command line):

```python
import staypresent

staypresent.run(bot_module="mypkg.bot")

```

It works the same way as `bot_file` everywhere else — pass a list for multiple bots, use `bot_args`/`env` for shared configuration, or mix file- and module-based bots together with per-bot config via `bots`:

```python
import staypresent

staypresent.run(bots=[
    {"file": "telegram_bot.py", "args": ["--verbose"]},        # a standalone script
    {"module": "discord_bot.worker", "env": {"SHARD": "0"}},   # a module inside a package
])

```

`bot_module`/`"module"` is mutually exclusive with `bot_file`/`"file"` — pass exactly one per bot. Unlike `bot_file`, a module path isn't checked for existence up front (verifying that safely would require importing it, which StayPresent deliberately avoids as a side effect) — a typo'd or missing module simply surfaces as that bot exiting non-zero, handled by the normal crash/restart logic above.

### How failures are handled with multiple bots

* Each bot has its own independent restart counter, so `max_restarts` is a *per-bot* budget.
* `staypresent.run()` waits for every bot to finish before returning or exiting — it doesn't stop supervising the others just because one of them gave up.
* If **any** bot ultimately fails to stay up (restarts exhausted, or `restart_on_crash=False` and it crashed), `staypresent.run()` exits the whole process with a non-zero exit code once every bot has finished, the same fail-loud behavior as the single-bot case.
* `Ctrl+C` / `SIGTERM` stops the web server and **all** bot processes cleanly.

---

## 📡 Self-Ping / Keep-Warm

Some free-tier hosts spin your service down after a period of inactivity, even if `staypresent.run()` has an open port. `staypresent.ping()`/`staypresent.cron()` let you periodically hit your own public URL to keep it warm — entirely optional and off by default.

### One-off ping

```python
import staypresent

result = staypresent.ping("https://my-bot.onrender.com")
print(result)
# {'url': 'https://my-bot.onrender.com/', 'ok': True, 'status_code': 200, 'elapsed': 0.42, 'error': None}

```

### Recurring keep-warm pings

```python
import staypresent

staypresent.web.json({"status": "online"})

handle = staypresent.cron("https://my-bot.onrender.com", interval=300)  # every 5 minutes

staypresent.run("bot.py")

```

`cron()` returns a `CronHandle` you can use to stop it later:

```python
handle.stop()               # stop the background pinger
handle.is_running           # True/False

```

You can also pass `on_success`/`on_failure` callbacks to react to each ping's result (e.g. for your own logging/metrics), and pass `host="127.0.0.1", port=8080` instead of a full URL if you just want to ping your own local server.

---

## ⚙️ API Reference

### `staypresent.run(...)`

Launch your bot script(s) alongside the web server.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `bot_file` | `str` or `list[str]` | `None` | Path to the Python script to run, or a list of paths to run several bots at once. Launched as `python <file> ...`. Mutually exclusive with `bot_module` and with `bots`. |
| `bot_module` | `str` or `list[str]` | `None` | Dotted module path (e.g. `"mypkg.bot"`) to run instead of a bare script, or a list of them. Launched as `python -m <module> ...`. Use this when your bot lives inside a package and needs package-relative imports — see [Bots that live inside a package](#bots-that-live-inside-a-package-bot_module). Mutually exclusive with `bot_file` and with `bots`. |
| `host` | `str` | `"0.0.0.0"` | Host to bind the web server to. |
| `port` | `int` | `8080` | Port to bind the web server to. |
| `production` | `bool` | `True` | Uses `waitress` if installed. Set to `False` to force the Flask dev server. |
| `threads` | `int` | `4` | Number of worker threads for `waitress`. Increase this if serving real web traffic rather than just keep-alive pings. *(Requires `production=True` and `waitress`)*. |
| `restart_on_crash` | `bool` | `True` | Relaunch a bot process if it exits with a non-zero exit code. |
| `max_restarts` | `int` | `5` | Maximum restart attempts per bot after a crash before giving up. |
| `restart_delay` | `float` | `2.0` | Seconds to wait before relaunching a bot process after a crash. |
| `restart_reset_after` | `float` | `60.0` | Seconds a bot must stay alive to reset its consecutive crash counter back to 0. |
| `bot_args` | `list` | `None` | Extra command-line arguments passed to every bot in `bot_file`/`bot_module` (e.g., `["--verbose"]`). Must be a list — a bare string like `"--flag"` raises a clear error instead of silently exploding into individual characters. Ignored when `bots` is used. |
| `env` | `dict` | `None` | Extra environment variables for every bot in `bot_file`/`bot_module`. Merges over the current environment. Ignored when `bots` is used. |
| `bots` | `list[dict]` | `None` | Per-bot configuration: `[{"file": "bot.py", ...}, {"module": "mypkg.bot", ...}, ...]` — each entry needs exactly one of `"file"`/`"module"`, plus optional `"args"`/`"env"`. Mutually exclusive with `bot_file`/`bot_module`/`bot_args`/`env` — see [Running Multiple Bots](#-running-multiple-bots). |

> **Note:** `port`, `threads`, `max_restarts`, `restart_delay`, and `restart_reset_after` are validated up front — passing an invalid value (e.g. `threads=0`, a negative `port`) raises a `ValueError` immediately instead of failing silently or deep inside `waitress`. Likewise, every bot file (in `bot_file` or `bots`) is checked to exist *before* the server starts.

### Crash Recovery Details

StayPresent automatically monitors every bot process. If one exits with a non-zero exit code, StayPresent restarts it based on your configuration:

* **Clean Exits:** An exit code of `0` is considered intentional and will *not* trigger a restart.
* **Independent Supervision:** With multiple bots, each one is monitored and restarted completely independently — one crashing (or exhausting its restarts) doesn't pause or stop the others.
* **Manual Shutdowns:** Stopping StayPresent via `Ctrl+C` (SIGINT) or `SIGTERM` shuts down the server and *every* bot process cleanly.
* **Smart Counters:** The `max_restarts` limit applies to *consecutive* crashes, per bot. If a bot runs successfully for the duration of `restart_reset_after` (default 60 seconds), its crash counter resets.
* **Non-Zero Exit on Giving Up:** `staypresent.run()` waits for every bot to finish. If any bot ultimately failed to stay up — restarts disabled and it crashed, or `max_restarts` was exhausted for it — `staypresent.run()` then exits the whole process with a non-zero exit code instead of returning normally. This lets a hosting platform's own restart-on-crash policy (Render, Railway, Docker, systemd, etc.) kick in as a last resort, instead of the process quietly exiting `0` as if nothing went wrong.

### `staypresent.web`

| Function | Description |
| --- | --- |
| `text(message, path="/")` | Serve plain text at `path`. |
| `json(data, path="/")` | Serve a JSON-serializable dict/list at `path`. A deep copy is stored. |
| `html(file_path, path="/")` | Serve an HTML file (read fresh every request) at `path`, plus its neighboring static assets. |
| `markdown(file_path, path="/", mode="auto", favicon=None, title=None, description=None)` | Serve a Markdown file, rendered to styled HTML (read + re-rendered fresh every request) at `path`, plus its neighboring static assets. See [Markdown Response](#markdown-response) for the theming/metadata parameters. |
| `remove(path="/")` | Stop hosting a response at `path`. Returns `True`/`False`. |
| `get(path="/")` | Returns `{"type": ..., "value": ...}` (plus `mode`/`favicon`/`title`/`description` for a Markdown entry) for `path`, or `{}` if nothing is registered there. |
| `get_all()` | Returns every registered path and its state as a single dict. |
| `paths()` | Returns a sorted list of every currently-registered path. |

### Built-in Health Check

A default `/health` endpoint is available out of the box, returning `{"status": "ok"}`. This is incredibly useful for platform pingers and uptime monitors that require a dedicated health-check path separate from your regular response(s). It's a default, not a reservation — registering your own response at `/health` via `staypresent.web` overrides it.

### `staypresent.ping(...)` / `staypresent.cron(...)`

| Function | Description |
| --- | --- |
| `ping(host, port=None, path="/", timeout=10.0, https=None)` | Send a single HTTP request and return `{"url", "ok", "status_code", "elapsed", "error"}`. |
| `cron(host, port=None, path="/", interval=300.0, repeat=True, timeout=10.0, https=None, on_success=None, on_failure=None)` | Start a background thread that pings a URL on a schedule. Returns a `CronHandle` (`.stop()`, `.is_running`). |

---

## 🪵 Logging

StayPresent logs to its own `"staypresent"` logger (via a dedicated `StreamHandler`), never touching Python's root logger — so it won't clobber, duplicate, or reformat log output your bot script has already configured for its own loggers. Startup, restarts, crashes, and shutdowns are all logged with timestamps at the appropriate level (`INFO`/`WARNING`/`ERROR`).

---

## 🛠 Requirements

* Python 3.8+
* Flask
* `waitress` *(optional, but highly recommended for production — `pip install staypresent[prod]`)*

Markdown rendering, theming, tables, and everything else in this README works with **no additional dependencies** — StayPresent ships its own built-in Markdown-to-HTML renderer.

---

## 💡 Use Cases

* Keeping a Discord/Telegram/Slack bot alive on a free-tier host that requires an open HTTP port.
* Running several bots (e.g. a Telegram bot *and* a Discord bot) from a single deployed service.
* Exposing a lightweight status page, uptime dashboard, or `CHANGELOG.md`/`README.md` viewer for a background worker.
* Giving a hosting platform's health-check probe something to hit while your real work happens in a separate process.
