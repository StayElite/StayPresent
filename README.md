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

**StayPresent** is a lightweight Python utility for keeping bots, workers, and background scripts running reliably on hosts that expect an active HTTP service.

It runs a dedicated Flask web server alongside your application, monitors your processes, automatically restarts crashed workers, and can detect processes that are still running but have become stuck using a simple heartbeat system.

It also includes a **built-in status dashboard** at `/status`, giving you uptime, restart counts, service states, and recent incidents without requiring a separate monitoring service.

Whether you need **a bot, a web server, or both**, StayPresent keeps the setup simple.

It supports running multiple bots under a single service, with each process monitored and restarted independently.

> Designed for platforms such as **Render, Railway, Koyeb, Heroku**, and other hosts that expect applications to keep an HTTP port open.

📖 **This README covers the essentials.**
For the complete configuration reference, deployment guide, web settings, process management, and FAQ, see the [full documentation](https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.mdd).

For release notes and changes, see the [changelog](https://github.com/StayElite/StayPresent/blob/main/CHANGELOG.mdd).

---

## ✨ Features

* **Zero-Friction Setup** — Start monitoring a bot with a single line of code.
* **Automatic Crash Recovery** — Automatically restart crashed processes with configurable delays and crash limits.
* **Hang Detection** — Detect processes that are running but frozen or deadlocked with `staypresent.heartbeat()`.
* **Built-in Status Dashboard** — Monitor uptime, process state, restart counts, and recent incidents at `/status`.
* **Multiple Bot Support** — Run and monitor multiple bots independently under one service.
* **Package-Aware Launching** — Launch bots located inside Python packages using relative imports with `bot_module`.
* **Production-Friendly Server** — Automatically uses `waitress` when available instead of Flask's development server.
* **Flexible Deployment** — Run bots without a web server, a web server without bots, or both together.
* **Custom HTTP Responses** — Serve plain text, JSON, HTML templates, or Markdown.
* **Built-in Markdown Rendering** — Render headings, lists, tables, code blocks, and GitHub-style Markdown without additional dependencies.
* **Theming Support** — Choose light, dark, or automatic OS-based themes.
* **Custom Routes** — Register multiple pages such as `/`, `/status`, `/dashboard`, or `/changelog`.
* **Static Assets** — Serve CSS, JavaScript, images, and favicons automatically, with configurable exclusions.
* **Optional Self-Ping** — Periodically ping your public URL to help prevent free-tier hosts from putting your service to sleep.

---

## 📦 Installation

Install StayPresent with pip:

```bash
pip install staypresent
```

### Production installation

For production deployments, install the optional `waitress` dependency:

```bash
pip install "staypresent[prod]"
```

This allows StayPresent to use Waitress instead of Flask's development server.

---

## 🚀 Quickstart

The simplest setup requires only one line:

```python
import staypresent

staypresent.run("bot.py")
```

StayPresent will launch your bot and provide a web service with a built-in status page.

### A more complete example

```python
import staypresent

staypresent.web.markdown(
    "CHANGELOG.md",
    path="/changelog",
    status=True,
)

staypresent.web.status(
    title="Groundflare Bot Status",
)

staypresent.run(
    "bot.py",
    host="0.0.0.0",
    port=5000,
    threads=8,
    heartbeat_timeout=30,
)
```

---

## 📊 Built-in Status Page

StayPresent automatically provides a live status page at:

```text
/status
```

For example:

```python
import staypresent

staypresent.run("bot.py")
```

You can customize the status page:

```python
staypresent.web.status(
    title="Groundflare Bot Status",
    copyright="Groundflare Inc.",
    footer_links=[
        {
            "label": "Support",
            "url": "https://support.groundflare/support",
        }
    ],
    mode="dark",
)
```

The status page can display information such as:

* Current service state
* Uptime
* Restart count
* Recent incidents
* Process health

No external monitoring service is required.

---

## 🤖 Running Multiple Bots

StayPresent can monitor multiple bot processes independently:

```python
import staypresent

staypresent.run([
    "telegram_bot.py",
    "discord_bot.py",
])
```

Each process is monitored separately and can be restarted independently if it crashes.

This makes it possible to host several bots under a single web service.

---

## 💓 Hang Detection

A process can be technically "running" while being completely stuck.

StayPresent provides a heartbeat mechanism for detecting this situation.

### Worker

```python
# worker.py

import staypresent

while True:
    staypresent.heartbeat()
    do_work()
```

### Application

```python
# app.py

import staypresent

staypresent.run(
    "worker.py",
    heartbeat_timeout=30,
)
```

If the worker stops sending heartbeats for longer than the configured timeout, StayPresent can treat it as unhealthy and restart it.

---

## 📡 Self-Ping / Keep-Warm

Some hosting platforms may suspend services that receive little or no traffic.

StayPresent includes an optional recurring HTTP ping:

```python
import staypresent

handle = staypresent.cron(
    "https://my-bot.onrender.com",
    interval=300,
)

staypresent.run("bot.py")
```

This sends a request every 300 seconds.

> Keep-warm behavior depends on your hosting provider's policies and should only be used where permitted by their terms.

---

## 🌐 Web Server

StayPresent can also be used without running a bot.

You can build a lightweight HTTP service with custom responses, pages, Markdown, status dashboards, and static assets.

For example, you can expose multiple routes:

```text
/
├── /status
├── /dashboard
└── /changelog
```

This makes StayPresent useful not only for bots, but also for lightweight background services and workers that need an HTTP endpoint.

---

## 🧩 API Overview

| API                       | Description                                     |
| ------------------------- | ----------------------------------------------- |
| `staypresent.run(...)`    | Launch one or more bots, a web server, or both. |
| `staypresent.heartbeat()` | Signal that a monitored process is still alive. |
| `staypresent.web.*`       | Register HTTP responses and pages.              |
| `staypresent.ping(...)`   | Send a single HTTP ping.                        |
| `staypresent.cron(...)`   | Schedule recurring background HTTP pings.       |

For the complete API and configuration reference, see the [documentation](https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.mdd).

---

## 🛠 Requirements

* `Python` **`3.8+`**
* `Flask`
* `waitress` — optional, but recommended for production deployments

---

## ☁️ Deployment

StayPresent is particularly useful on platforms that expect your application to expose an HTTP port, including:

* **Render**
* **Railway**
* **Koyeb**
* **Heroku**
* Other platforms that require a long-running HTTP service

A typical deployment can run your bot and web server together:

```python
import staypresent

staypresent.run(
    "bot.py",
    host="0.0.0.0",
    port=5000,
)
```

This allows the hosting platform to detect an active HTTP service while StayPresent manages your background process.

---

## 📚 Documentation

* **[Full Documentation](https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.mdd)** — Configuration, deployment, web settings, process management, and FAQ.
* **[Changelog](https://github.com/StayElite/StayPresent/blob/main/CHANGELOG.mdd)** — Releases and changes.

---

## ❤️ Why StayPresent?

Running a bot on a hosting platform shouldn't require a complicated monitoring stack.

StayPresent combines:

**Process management + crash recovery + heartbeat monitoring + HTTP server + status dashboard**

into a single lightweight Python package.

```python
import staypresent

staypresent.run("bot.py")
```

That's the idea behind StayPresent:

> **Keep your process present. Keep your service alive.**
