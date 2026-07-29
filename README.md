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

A lightweight Python package that keeps your bots and background scripts alive by running a dedicated Flask web server alongside your main application(s).

Perfect for deploying on platforms like **Render**, **Railway**, **Koyeb**, **Heroku**, or any host that requires an active HTTP port to keep your service running.

📖 **This README covers the essentials.** For the full guide — every parameter, every `staypresent.web` option, deployment notes, and a detailed FAQ — see **[DOCUMENTATION.md](DOCUMENTATION.md)**. Release notes live in **[CHANGELOG.md](CHANGELOG.md)**.

---

## ✨ Features

* **Zero-Friction Setup:** Get running with one line of code.
* **Production-Ready by Default:** Automatically uses `waitress` when installed, avoiding Flask's "development server" warning.
* **Multiple Bot Support:** Run several bot processes side-by-side under one web server, each monitored and restarted independently.
* **Package-Aware Bot Launching:** Launch a bot that lives inside a package (and needs relative imports) as a proper module via `bot_module`.
* **Auto-Restarts & Crash Recovery:** Automatically respawns a crashed bot process, with configurable delay and consecutive-crash budget, per bot.
* **Flexible Responses:** Serve plain text, JSON (default), full HTML templates, or rendered Markdown.
* **Built-in Markdown Renderer — Zero Extra Dependencies:** Headings, emphasis, links, images, nested lists, tables, code blocks, raw HTML passthrough, and a GitHub-flavored stylesheet, with no `markdown` package required.
* **Light / Dark / Auto Theming:** Markdown pages can follow the visitor's OS preference or be forced to `light`/`dark`.
* **Custom Paths, Multiple Responses:** Host more than one response at once, at different paths (e.g. `/`, `/status`, `/dashboard`).
* **Static Asset Serving:** CSS, JS, images, and favicons next to your HTML/Markdown files are served automatically.
* **Optional Self-Ping / Keep-Warm:** Periodically ping your own public URL to stop free-tier hosts spinning your service down — off by default.

See **[DOCUMENTATION.md](DOCUMENTATION.md)** for the full feature list, including advanced process control and fail-safe logging.

---

## 📦 Installation

```bash
pip install staypresent
```

**Recommended for production** — installs [`waitress`](https://pypi.org/project/waitress/) to suppress Flask's dev-server warning:

```bash
pip install staypresent[prod]
```

If `waitress` isn't installed, StayPresent falls back to Flask's built-in server and logs a one-time warning — everything else (Markdown rendering, theming, tables, etc.) works with no extra dependencies either way.

---

## 🚀 Quickstart

```python
import staypresent

staypresent.run("bot.py")
```

That's it. This starts a background web server (`0.0.0.0:8080`, serving `{"message": "I'm Present"}` at `/`) and runs `bot.py` alongside it, automatically restarting it if it ever crashes.

### A more complete example

```python
import staypresent

staypresent.web.markdown("CHANGELOG.md")   # render a status/changelog page at "/"
staypresent.run(
    "bot.py",
    host="0.0.0.0",
    port=5000,
    threads=8,
)
```

Every `staypresent.web` function (`text`, `json`, `html`, `markdown`) accepts a `path=` argument, so you can host several independent responses — e.g. a JSON status at `/`, a dashboard at `/dashboard`, a changelog at `/changelog` — all from the same server. See **[Custom Paths & Multiple Responses](DOCUMENTATION.md#35-custom-paths--multiple-responses)** for the details.

---

## 🤖 Running Multiple Bots

```python
import staypresent

staypresent.run(["telegram_bot.py", "discord_bot.py"])
```

Each bot is supervised and restarted independently. For per-bot arguments/environment, or for a bot that needs `python -m` (package-relative imports), use `bots=[...]` / `bot_module=...` — see **[Process Execution](DOCUMENTATION.md#4-process-execution-staypresentrun)** for the full reference.

---

## 📡 Self-Ping / Keep-Warm

```python
import staypresent

handle = staypresent.cron("https://my-bot.onrender.com", interval=300)  # every 5 minutes
staypresent.run("bot.py")
```

Fully optional, off by default. See **[Self-Ping / Keep-Warm](DOCUMENTATION.md#5-self-ping--keep-warm-staypresentping--staypresentcron)**.

---

## ⚙️ API Reference (quick glance)

| | |
| --- | --- |
| `staypresent.run(bot_file=None, host="0.0.0.0", port=8080, ...)` | Launch your bot(s) alongside the web server. |
| `staypresent.web.text/json/html/markdown(..., path="/")` | Register a response at a path. |
| `staypresent.web.remove/get/get_all/paths()` | Inspect or remove registered responses. |
| `staypresent.ping(host, ...)` | Send a single one-off HTTP ping. |
| `staypresent.cron(host, ...)` | Start a recurring background ping (`CronHandle`). |
| `staypresent.active_cron_handles()` | List every currently-running cron pinger. |

Every parameter, default, and validation rule is documented in full in **[§8 API Reference](DOCUMENTATION.md#8-api-reference)** of DOCUMENTATION.md, along with **[§4 Process Execution](DOCUMENTATION.md#4-process-execution-staypresentrun)** (crash recovery, multi-bot, `bot_module`) and **[§3 Web Server Configuration](DOCUMENTATION.md#3-web-server-configuration-staypresentweb)** (all response types, theming, static assets).

A built-in `/health` endpoint (`{"status": "ok"}`) is available out of the box for uptime monitors — see **[§6](DOCUMENTATION.md#6-built-in-health-check)**.

---

## 🛠 Requirements

* Python 3.8+
* Flask
* `waitress` *(optional, recommended for production — `pip install staypresent[prod]`)*

Markdown rendering, theming, and tables work with **no additional dependencies** — StayPresent ships its own built-in Markdown-to-HTML renderer.

---

## 💡 Use Cases

* Keeping a Discord/Telegram/Slack bot alive on a free-tier host that requires an open HTTP port.
* Running several bots (e.g. a Telegram bot *and* a Discord bot) from a single deployed service.
* Exposing a lightweight status page, uptime dashboard, or `CHANGELOG.md` viewer for a background worker.
* Giving a hosting platform's health-check probe something to hit while your real work happens in a separate process.

---

📖 For everything else — full parameter tables, deployment notes, and an FAQ covering restarts, path collisions, `bot_module`, and more — see **[DOCUMENTATION.md](DOCUMENTATION.md)**.