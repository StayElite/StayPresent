"""
StayPresent - Bot Status Registry

Tracks each bot's live status (operational/degraded/offline), uptime,
restart count, and recent incidents - purely from what runner.py already
observes (process launches, crashes, restarts, hangs, permanent
failures). This is the data staypresent.web.status()'s built-in status
page renders, so that page shows real, automatically-derived signals
instead of anything the person has to compute or report themselves.
Nothing here is ever fabricated: a metric StayPresent doesn't actually
know is simply absent from the snapshot, not filled in with a
placeholder number.

Part of the StayPresent project.
Docs: https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.md
"""

# Created and maintained by Ashish Sharma (Stay Elite).
# Copyright (c) 2026 Ashish Sharma (Stay Elite)
# Licensed under the MIT License. See the LICENSE file for details.

import collections
import copy
import os
import threading
import time

_lock = threading.Lock()
_bots = {}  # index -> live state dict, see reset() below

# Capped so a bot that crash-loops for weeks doesn't grow this without
# bound. Kept generous (rather than the old cap of 20) so the status
# page's "full history" view (see _MAX_INCIDENTS_HISTORY below) actually
# has more than the default recent-20 view to show.
_MAX_INCIDENTS_PER_BOT = 200

# Default number of merged, all-bots incidents snapshot() returns - the
# normal, "recent activity" view of the status page.
_MAX_INCIDENTS_DISPLAYED = 20

# Cap for the expanded "full history" view (see snapshot()'s
# incident_limit param) - still bounded, just much larger than the
# default, so a status page with many bots and a long history doesn't
# return an unbounded response.
_MAX_INCIDENTS_HISTORY = 200

# How many recent stdout/stderr lines each bot keeps in memory (a rolling
# buffer - runner.py appends to it continuously via append_log() from a
# dedicated reader thread per stream). Bounded so a chatty or long-running
# bot can't grow this without limit.
_MAX_LOG_LINES_PER_BOT = 300

# How many of those lines actually go out in an admin snapshot - kept
# smaller than the in-memory buffer above so a status-page fetch stays
# small even when the full buffer is nearly maxed out; this is a "recent
# tail", not a full log viewer.
_LOG_LINES_IN_SNAPSHOT = 50

# A single captured line longer than this is truncated before being
# stored at all - protects both memory and the eventual JSON payload from
# a bot that (accidentally or not) prints one enormous line (a huge
# single-line stack trace, or non-text/binary output).
_MAX_LOG_LINE_CHARS = 2000

_STATE_RANK = {"operational": 0, "degraded": 1, "offline": 2}

# Rolling uptime windows shown on the status page, alongside the
# lifetime-since-started figure that already existed. Label -> seconds.
_UPTIME_WINDOWS = {
    "uptime_24h": 24 * 60 * 60,
    "uptime_7d": 7 * 24 * 60 * 60,
    "uptime_30d": 30 * 24 * 60 * 60,
}

# How far back a *closed* down period is kept in the live "down_periods"
# list before being rolled into a single cumulative total instead (see
# _trim_down_periods below). Matches the widest rolling window above -
# anything older than this can no longer affect uptime_24h/7d/30d, so the
# only thing that still needs it is the lifetime uptime figure, which
# _uptime_pct's `extra_down` param covers via that cumulative total. Keeps
# a bot that crash-loops occasionally over months from growing this list
# without bound (the same problem _MAX_INCIDENTS_PER_BOT solves for
# incidents).
_MAX_DOWN_PERIOD_AGE = max(_UPTIME_WINDOWS.values())

# The pseudo-bot file_key used to track the web server thread itself (see
# runner.py's `track_web_server` usage of reset() below) - StayPresent's
# supervision previously only ever covered bot processes, leaving the
# status page blind to the web server thread dying on its own (e.g. an
# unhandled error inside waitress after a successful startup). Tracked
# the same way a bot is - one more entry in `_bots`, keyed by the index
# right after the last real bot - so it gets its own row, uptime figures,
# and incident trail for free from everything below. `snapshot()` below
# normally expands this single entry into one row per registered
# `staypresent.web.*()` route (see `_web_route_service_labels()`) rather
# than showing one generic "Web Server" row regardless of how many pages
# are actually being served - the same reasoning a real bot's default
# name comes from its own file/module path rather than a generic "Bot".
# Overridable via `services_name`/`services_description` (key
# `"web_server"`) via staypresent.run() or any
# staypresent.web.html()/json()/text()/markdown() call, the same as a
# real bot's file/module key - an explicit override name collapses back
# down to a single row (see snapshot()), since a developer who bothered
# to name it themselves almost certainly means it as one thing.
WEB_SERVER_FILE_KEY = "web_server"

# Process-wide name/description overrides set via `set_global_service_
# overrides()` below - the shared backing store for every
# `services_name`/`services_description` a caller has set for a given
# bot/web-server key, keyed the same way `_bots` is (the file/module
# string given to bot_file/bot_module/bots[i]['file'/'module'], or
# WEB_SERVER_FILE_KEY for the web server thread's own row). Unlike the
# old dict-based `staypresent.web.services()` (removed - see
# update_service_override() below), there is no single caller that owns
# the whole map: each key is set independently, by whichever of
# staypresent.run() (single-bot/no-bot convenience), a bot's own
# `bots[i]['services_name'/'services_description']` entry, or a
# `staypresent.web.html()`/`json()`/`text()`/`markdown()` call last
# touched that particular key - see update_service_override().
_global_service_overrides = {}

# A `services_name`/`services_description` given directly to one of
# `staypresent.web.html()`/`json()`/`text()`/`markdown()` (or to
# `staypresent.run()` itself) doesn't know its own target key yet - that
# depends on how many bots end up configured, which isn't decided until
# `staypresent.run()` actually runs `reset()` below. So a call naming a
# plain string (not a per-bot dict entry) is stashed here first and only
# resolved to a real key by `resolve_pending_single_target_override()`,
# called from `reset()`. Last call wins - the same "whichever call
# happens last" rule the rest of this module follows - so a
# `staypresent.run(services_name=...)` given after an earlier
# `staypresent.web.markdown(services_name=...)` replaces it outright.
_pending_single_target_override = None


def _validate_optional_str(value, param_name: str, caller: str) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{caller}: '{param_name}' must be a str or None, got {type(value).__name__}.")


def update_service_override(key: str, name: str = None, description: str = None, caller: str = "staypresent") -> None:
    """
    Set/merge the display name and/or description shown for `key`'s row
    on the status page. `key` is the same file/module string given to
    bot_file/bot_module/bots[i]['file'/'module'] for a real bot, or
    WEB_SERVER_FILE_KEY for the web server thread's own row - a key that
    doesn't match any actual bot still gets its own row, useful for an
    external dependency (e.g. a database, a third-party API) StayPresent
    doesn't itself supervise.

    `name`/`description` are each merged in independently: leaving one as
    None here does NOT clear a value already set for `key` by an earlier
    call - only an explicit (non-None) value ever changes a field. This
    lets e.g. `staypresent.web.markdown(services_name=...)` (which has no
    reason to also repeat `services_description`) and a later
    `staypresent.run(services_description=...)` each contribute their own
    half without one call clobbering the other's.
    """
    if not isinstance(key, str) or not key:
        raise TypeError(f"{caller}: service override key must be a non-empty str, got {key!r}.")
    _validate_optional_str(name, "services_name", caller)
    _validate_optional_str(description, "services_description", caller)
    if name is None and description is None:
        return
    global _global_service_overrides
    with _lock:
        entry = dict(_global_service_overrides.get(key, {}))
        if name is not None:
            entry["name"] = name
        if description is not None:
            entry["description"] = description
        _global_service_overrides = {**_global_service_overrides, key: entry}


def set_pending_single_target_override(name: str = None, description: str = None, caller: str = "staypresent") -> None:
    """
    Stash a `services_name`/`services_description` given as a plain
    string (not a per-bot dict entry) - see `_pending_single_target_override`
    above for why this can't be applied to a real key yet. A no-op call
    (both None) still clears out whatever the previous call staged, the
    same last-call-wins behavior as everywhere else here.
    """
    _validate_optional_str(name, "services_name", caller)
    _validate_optional_str(description, "services_description", caller)
    global _pending_single_target_override
    if name is None and description is None:
        _pending_single_target_override = None
        return
    _pending_single_target_override = {"name": name, "description": description, "caller": caller}


def resolve_pending_single_target_override(bot_configs: list) -> None:
    """
    Called from `reset()`, once `staypresent.run()` finally knows how
    many bots this process actually has, to turn whatever
    `set_pending_single_target_override()` staged into a real
    `update_service_override()` call:

      - Exactly one bot configured: that bot's own file/module string.
      - No bots configured (web server only): `WEB_SERVER_FILE_KEY`.
      - Two or more bots configured: raises `TypeError` - a single plain
        string can't unambiguously mean any one of them. Tag each bot
        individually instead, via
        `bots=[{"file": "a.py", "services_name": "Bot A"}, ...]`.

    A no-op if nothing is pending.
    """
    global _pending_single_target_override
    pending = _pending_single_target_override
    if pending is None:
        return
    _pending_single_target_override = None
    if len(bot_configs) > 1:
        raise TypeError(
            f"{pending['caller']}: 'services_name'/'services_description' given as a plain "
            "str only work when there's exactly one bot (or none) running in this process - "
            "with multiple bots, tag each one individually instead, e.g. "
            "bots=[{'file': 'a.py', 'services_name': 'Bot A'}, {'file': 'b.py', "
            "'services_name': 'Bot B'}]."
        )
    if len(bot_configs) == 1:
        cfg = bot_configs[0]
        key = cfg.get("file") or cfg.get("module")
    else:
        key = WEB_SERVER_FILE_KEY
    update_service_override(key, pending["name"], pending["description"], caller=pending["caller"])


# Type -> human label used by _label_for_web_route()'s final fallback
# below (e.g. a bare json()/text() route with no path or title worth
# showing still gets something more specific than "Web Server").
_WEB_ROUTE_TYPE_LABELS = {
    "json": "JSON", "text": "Text", "html": "HTML",
    "markdown": "Markdown", "status": "Status",
}


def _label_for_web_route(path: str, entry: dict) -> str:
    """
    Turn one `staypresent.web.*()` route registration into a short,
    human label - used both to name that route's own row on the status
    page (see `_web_route_service_labels()` above) and, historically, to
    name the web server's row as a whole before per-route rows existed.
    Priority order:

      1. The route's own path (e.g. "/dashboard" -> "Dashboard") -
         usually the most distinctive thing about a given route, and
         normally what a developer would call it themselves.
      2. `path == "/"` carries no distinguishing information on its own
         (nearly every project has *something* at "/"), so fall back to
         a page title instead: `markdown()`'s own `title=`, or an
         `html()`/`markdown()` file's own filename when no explicit
         title was given.
      3. Still nothing (e.g. a bare `json()`/`text()` route registered
         at "/") - fall back to the response type itself (e.g. "JSON").
    """
    if path and path != "/":
        label = path.strip("/").replace("_", " ").replace("-", " ").strip()
        if label:
            return label.title()

    title = entry.get("title")
    if title:
        return title

    if entry.get("type") in ("html", "markdown"):
        value = entry.get("value")
        if value:
            stem = os.path.splitext(os.path.basename(value))[0]
            if stem:
                return stem.replace("_", " ").replace("-", " ").title()

    return _WEB_ROUTE_TYPE_LABELS.get(entry.get("type"), "Web Server")


def _web_route_service_labels() -> list:
    """
    One `(name, description)` pair per currently-registered
    `staypresent.web.*()` route, in registration order - the actual
    logic behind expanding the web server's single supervised thread
    into one status-page row per page/response it's serving (see
    `snapshot()` below), instead of collapsing every registered route
    into one row with one name (which is either uninformative, when
    it's a generic fallback, or actively misleading, when it happens to
    be named after whichever route registered first regardless of
    relevance - both problems an earlier version of this had).

    A visitor cares about "is my changelog page up" and "is my status
    page up" as two separate questions, even though StayPresent only
    ever supervises the one underlying web-server thread that serves
    both - so every row this returns is meant to share that thread's
    real, live status/uptime/incident data (done by the caller), just
    labeled per-route here.

    Each route's name comes from `_label_for_web_route()` below; two
    routes that happen to produce the same label (e.g. two `html()`
    pages both named "index") are disambiguated by appending each one's
    own path, so no route silently vanishes into an indistinguishable
    duplicate row. Every name also gets a trailing " - Web" so it's
    instantly recognizable as a web route rather than a supervised bot
    process at a glance on the status page (e.g. "Status" -> "Status -
    Web"). Each route's description, if any (`markdown()`'s own
    `description=`), travels with it - falling back to an empty string,
    left for the caller to fill in from the process-wide
    `services_description` override instead, same as any other service.

    Lazily imports `web` (rather than a module-level import) since
    `web.py` already imports this module at import time - a top-level
    `import . web` here would be circular. Safe to do inside a function:
    by the time this actually runs (`staypresent.run()` mid-call, or a
    status-page poll), both modules are already fully loaded.
    """
    from . import web as _web  # local import: web.py imports this module

    with _web._lock:
        routes = list(_web._routes.items())

    # Each staypresent.web.*() call takes its own `status=True/False`
    # (default False - opt-in) controlling whether *that* route gets a
    # row on the status page at all. Filtered here rather than in
    # web.py itself so web.py stays a plain, status-page-agnostic route
    # registry - this is the one place that turns registrations into
    # status-page rows.
    routes = [(path, entry) for path, entry in routes if entry.get("status") is True]

    labeled = [(path, _label_for_web_route(path, entry), entry) for path, entry in routes]
    name_counts = {}
    for _, name, _entry in labeled:
        name_counts[name] = name_counts.get(name, 0) + 1

    result = []
    for path, name, entry in labeled:
        if name_counts[name] > 1:
            name = f"{name} ({path})"
        # " - Web" suffix so every expanded row is instantly
        # recognizable as a web route (as opposed to a supervised bot
        # process) at a glance on the status page - e.g. "Changelog" ->
        # "Changelog - Web", "Status" -> "Status - Web".
        result.append((f"{name} - Web", entry.get("description") or ""))
    return result


def _new_bot_state(now: float, file_key, is_module: bool, display_name, status_visible: bool = True) -> dict:
    return {
        "file_key": file_key,
        "is_module": is_module,
        "display_name": display_name,
        # Whether this bot gets its own row on the status page at all -
        # see reset()'s `bot_status` param below (fed from
        # staypresent.run()'s own `status`/per-bot `bots[i]['status']`).
        # True (shown) by default. This only ever hides/shows the row;
        # the bot itself is supervised (launched, restarted on crash,
        # etc.) exactly the same either way - this never affects
        # anything except what snapshot() below renders.
        "status_visible": bool(status_visible),
        "state": "operational",
        "first_started_at": now,
        # List of [start_ts, end_ts_or_None] - one entry per period this
        # bot was NOT running (crashed, hung, permanently failed, or
        # cleanly exited). An open period (end is None) means it's down
        # right now. This is the single source of truth for every uptime
        # figure below (lifetime and rolling-window) - replaces the old
        # down_since/down_seconds pair with something that can actually
        # answer "how much downtime in just the last 24h?".
        "down_periods": [],
        # Cumulative seconds of downtime rolled out of the list above by
        # _trim_down_periods once a closed period is older than every
        # rolling window - still added back into the *lifetime* uptime
        # figure (see _uptime_pct's extra_down param) since that one
        # covers all of history, not just the last 30 days.
        "down_before_cutoff": 0.0,
        "restart_count": 0,
        "last_exit_code": None,
        "permanently_failed": False,
        "incidents": [],
        "log": collections.deque(maxlen=_MAX_LOG_LINES_PER_BOT),
    }


def reset(
    bot_configs: list,
    display_names: list = None,
    track_web_server: bool = False,
    bot_status: list = None,
) -> None:
    """
    (Re)initialize the registry for a fresh staypresent.run() call: one
    live-state entry per bot in `bot_configs`, plus one more for the web
    server thread itself when `track_web_server` is True. Safe to call
    again (e.g. in tests) - it fully replaces whatever was tracked before.

    `bot_status`, if given, is a list parallel to `bot_configs` - each
    entry is the already-resolved (per-bot override, falling back to
    `staypresent.run()`'s own `status=`) True/False visibility for that
    bot's row on the status page. `None` (or a shorter list than
    `bot_configs`) treats a missing entry as visible (True) - the same
    "shown unless explicitly disabled" default `staypresent.run()`
    itself uses. This only controls whether that bot gets a row on the
    status page; it's supervised (launched, restarted on crash, etc.)
    identically either way.

    `display_names`, if given, is runner.py's own already-disambiguated
    name for each bot (see `_disambiguated_bot_names()` there) - the same
    one used in log lines, promoted from a bare filename to a full path
    whenever two bots in this run share a filename (e.g. "shard_a/bot.py"
    vs "shard_b/bot.py"). Used as this bot's default status-page name
    (before any `services_name` override) so two same-named bots don't
    show up as two identical, indistinguishable rows. Falls back to a
    plain basename derived from `bot_configs` itself when not given (e.g.
    a direct call to this function in tests, without going through
    run()).

    `track_web_server`, when True, adds one extra entry (index
    `len(bot_configs)`) for the web server thread - its default display
    name is "Web Server", overridable the same way a real bot's is, via a
    `services_name`/`services_description` entry (key `"web_server"`)
    passed to `staypresent.run()` or `staypresent.web.status()`. Note
    this is only the *fallback* raw state; `snapshot()` below normally
    expands this single entry into one row per registered
    `staypresent.web.*()` route rather than showing this name as-is (see
    `_web_route_service_labels()`).
    """
    now = time.time()
    with _lock:
        _bots.clear()
        for i, cfg in enumerate(bot_configs):
            file_val = cfg.get("file")
            module_val = cfg.get("module")
            visible = True
            if bot_status is not None and i < len(bot_status) and bot_status[i] is not None:
                visible = bool(bot_status[i])
            _bots[i] = _new_bot_state(
                now,
                file_val or module_val,
                file_val is None and module_val is not None,
                display_names[i] if display_names else None,
                status_visible=visible,
            )
        if track_web_server:
            web_index = len(bot_configs)
            _bots[web_index] = _new_bot_state(now, WEB_SERVER_FILE_KEY, False, "Web Server")
    resolve_pending_single_target_override(bot_configs)


def _is_down(bot: dict) -> bool:
    return bool(bot["down_periods"]) and bot["down_periods"][-1][1] is None


def _trim_down_periods(bot: dict, now: float) -> None:
    """Roll any *closed* down period older than _MAX_DOWN_PERIOD_AGE out
    of the live list and into `down_before_cutoff` (a running total)
    instead - called on every open/close transition, which is exactly
    when a bot that crash-loops occasionally would otherwise keep growing
    this list forever. The currently-open period (if any) is never
    trimmed, since it hasn't ended yet."""
    cutoff = now - _MAX_DOWN_PERIOD_AGE
    periods = bot["down_periods"]
    kept = []
    changed = False
    for period in periods:
        start, end = period
        if end is not None and end < cutoff:
            bot["down_before_cutoff"] = bot.get("down_before_cutoff", 0.0) + (end - start)
            changed = True
            continue
        kept.append(period)
    if changed:
        bot["down_periods"] = kept


def _open_down_period(bot: dict, now: float) -> None:
    if not _is_down(bot):
        bot["down_periods"].append([now, None])
    _trim_down_periods(bot, now)


def _close_down_period(bot: dict, now: float) -> None:
    if _is_down(bot):
        bot["down_periods"][-1][1] = now
    _trim_down_periods(bot, now)


def _down_seconds_in_window(down_periods: list, now: float, window_start: float) -> float:
    """Total seconds of downtime that overlap [window_start, now], given
    a list of [start, end_or_None] periods (end=None meaning still down).
    Used both for the lifetime uptime figure (window_start=the bot's own
    first_started_at) and the rolling 24h/7d/30d windows."""
    total = 0.0
    for start, end in down_periods:
        period_end = now if end is None else end
        overlap_start = max(start, window_start)
        overlap_end = min(period_end, now)
        if overlap_end > overlap_start:
            total += overlap_end - overlap_start
    return total


def _uptime_pct(bot: dict, now: float, window_start: float, extra_down: float = 0.0) -> float:
    """`extra_down` adds in downtime that's no longer in `down_periods`
    at all (see `_trim_down_periods`/`down_before_cutoff` above) - only
    meaningful for the *lifetime* figure (window_start=the bot's own
    first_started_at), since anything old enough to have been trimmed is,
    by construction, already outside every rolling 24h/7d/30d window."""
    elapsed = now - window_start
    if elapsed <= 0:
        return 100.0
    down = _down_seconds_in_window(bot["down_periods"], now, window_start) + extra_down
    return round(max(0.0, min(100.0, (elapsed - down) / elapsed * 100)), 2)


def _add_incident(bot: dict, event: str, status: str, exit_code=None, log_line=None) -> None:
    bot["incidents"].insert(0, {
        "event": event, "status": status, "exit_code": exit_code,
        "log_line": log_line, "time": time.time(),
    })
    del bot["incidents"][_MAX_INCIDENTS_PER_BOT:]


def _last_nonempty_log_line(bot: dict):
    """Most recent non-blank captured stdout/stderr line, or None if the
    bot hasn't produced any (or hasn't started) - used to attach a bit of
    concrete context (e.g. the actual exception message) to a crash
    incident, on top of the bare exit code."""
    for entry in reversed(bot["log"]):
        if entry["line"].strip():
            return entry["line"]
    return None


def append_log(index: int, stream: str, line: str) -> None:
    """
    Record one line of a bot's captured stdout/stderr output, for
    admin-only display on the status page (a "last log" tail per
    service) and to give crash incidents a concrete last-line-seen
    beyond just the exit code.

    Called continuously while a bot is alive - runner.py reads each of
    its process's stdout/stderr streams on its own dedicated thread and
    forwards every line here as it arrives. `stream` is "stdout" or
    "stderr"; `line` should already have its trailing newline stripped.
    """
    if len(line) > _MAX_LOG_LINE_CHARS:
        line = line[:_MAX_LOG_LINE_CHARS] + f"... [truncated, {len(line)} chars total]"
    with _lock:
        bot = _bots.get(index)
        if bot is None:
            return
        bot["log"].append({"stream": stream, "line": line, "time": time.time()})


def mark_started(index: int) -> None:
    """A bot's process (first launch, or a restart) just started running."""
    now = time.time()
    with _lock:
        bot = _bots.get(index)
        if bot is None:
            return
        _close_down_period(bot, now)
        bot["state"] = "operational"


def mark_recovered(index: int) -> None:
    """
    A bot has now been running continuously for at least
    restart_reset_after seconds since its last crash/restart (see
    runner.py's recovery-check timer) - treated as genuinely stable, not
    just "restarted a moment ago". Closes out the incident trail with an
    explicit "resolved" entry, instead of leaving the most recent
    incident stuck at "investigating"/"identified" forever even though
    the bot has been fine for a while.

    A no-op if there's nothing to resolve (no incidents yet, already
    resolved, or the bot gave up for good) - runner.py's timer can fire
    this speculatively without needing to know the bot's incident state
    itself.
    """
    with _lock:
        bot = _bots.get(index)
        if bot is None:
            return
        if bot["permanently_failed"]:
            return
        if not bot["incidents"]:
            return
        if bot["incidents"][0]["event"] == "recovered":
            return
        _add_incident(bot, event="recovered", status="resolved")


def mark_unresponsive(index: int) -> None:
    """
    A bot's process is still running but has not sent a heartbeat within
    the configured timeout (see runner.py's heartbeat watchdog thread,
    only active when staypresent.run(heartbeat_timeout=...) is set).
    Recorded as its own incident distinct from a crash, since the process
    hasn't actually exited yet - runner.py terminates it right after
    calling this, which will separately trigger mark_crashed() once
    process.wait() unblocks, giving a clear two-step trail: "stopped
    responding" followed by "crashed (terminated), restarting".
    """
    now = time.time()
    with _lock:
        bot = _bots.get(index)
        if bot is None:
            return
        bot["state"] = "degraded"
        _open_down_period(bot, now)
        _add_incident(
            bot, event="unresponsive", status="investigating",
            log_line=_last_nonempty_log_line(bot),
        )


def mark_crashed(index: int, exit_code: int, will_restart: bool) -> None:
    """A bot's process just exited with a non-zero code."""
    now = time.time()
    with _lock:
        bot = _bots.get(index)
        if bot is None:
            return
        bot["state"] = "degraded" if will_restart else "offline"
        _open_down_period(bot, now)
        bot["last_exit_code"] = exit_code
        if will_restart:
            bot["restart_count"] += 1
        _add_incident(
            bot,
            event="crash_restarting" if will_restart else "crash_no_restart",
            status="investigating" if will_restart else "identified",
            exit_code=exit_code,
            log_line=_last_nonempty_log_line(bot),
        )


def mark_permanently_failed(index: int, exit_code) -> None:
    """A bot exhausted max_restarts (or restart_on_crash=False) and gave up for good."""
    now = time.time()
    with _lock:
        bot = _bots.get(index)
        if bot is None:
            return
        bot["state"] = "offline"
        bot["permanently_failed"] = True
        _open_down_period(bot, now)
        bot["last_exit_code"] = exit_code
        _add_incident(
            bot, event="permanent_failure", status="identified",
            exit_code=exit_code, log_line=_last_nonempty_log_line(bot),
        )


def mark_web_server_down(index: int, detail: str = None, failed_to_start: bool = False) -> None:
    """
    The web server thread either failed to start at all
    (`failed_to_start=True`), or started successfully and then died
    unexpectedly later (see runner.py's `_watch_server_thread`) - e.g. an
    unhandled error inside waitress mid-run. Unlike a bot, StayPresent
    doesn't itself restart the web server, so this is always terminal for
    the current `run()` - there's no "will_restart" branch the way
    `mark_crashed` has.

    The two cases get distinct incident text (an admin reading "stopped
    unexpectedly" for something that in fact never came up at all would
    be misled about what actually happened) - the public-facing title is
    the same generic "unavailable" either way, since that distinction
    isn't meaningful to a plain visitor.

    `detail`, if given, is attached to the incident the same way a bot
    crash's last-log-line is - admin-only extra context (e.g. the
    exception message), never shown to a plain visitor.
    """
    now = time.time()
    with _lock:
        bot = _bots.get(index)
        if bot is None:
            return
        bot["state"] = "offline"
        bot["permanently_failed"] = True
        _open_down_period(bot, now)
        event = "web_server_failed_to_start" if failed_to_start else "web_server_down"
        _add_incident(bot, event=event, status="identified", log_line=detail)


def mark_clean_exit(index: int) -> None:
    """A bot exited with code 0 (intentional) and isn't being restarted."""
    now = time.time()
    with _lock:
        bot = _bots.get(index)
        if bot is None:
            return
        bot["state"] = "offline"
        _open_down_period(bot, now)
        bot["last_exit_code"] = 0
        # Not an incident: an intentional, clean exit isn't a problem to
        # report, just a status change - the "offline" badge already
        # reflects that this bot is no longer running.


def _display_name(file_key, override: dict, fallback_display_name: str = None, is_module: bool = False, bot_id: int = None) -> str:
    name = override.get("name") if override else None
    if name:
        return name
    
    if fallback_display_name is not None:
        # A real bot: fallback_display_name is runner.py's own
        # already-disambiguated identifier (see reset()) - the short
        # filename normally, promoted to the full path whenever it
        # collides with another bot's in this run (e.g. "shard_a/bot.py"
        # vs "shard_b/bot.py").
        if is_module:
            # A dotted module path (e.g. "mypkg.worker") has no file
            # extension to strip - shown as-is instead.
            return f"{fallback_display_name} - Worker"
        
        stem = os.path.splitext(os.path.basename(fallback_display_name))[0] or fallback_display_name
        parent = os.path.basename(os.path.dirname(file_key)) if file_key else ""
        return f"{parent}/{stem} - Worker" if parent else f"{stem} - Worker"
        
    if not file_key:
        # Unique identifier for the ultimate fallback, preventing multiple 
        # completely unknown entries from blending together.
        if bot_id is not None:
            return f"Service (Unknown ID: {bot_id})"
        return "Service (Unknown)"
        
    # Unlike fallback_display_name above (always a real bot's own
    # filename/module path), this file_key is an arbitrary label the
    # developer chose for a `services=` entry with no matching bot - e.g.
    # "api.example.com" or a hierarchical key like "us-east/database".
    # By returning file_key unmodified, we skip os.path.basename() and 
    # ensure custom hierarchical naming structures remain fully intact.
    return file_key


def _format_time(ts: float) -> str:
    return time.strftime("%b %d, %Y at %I:%M %p UTC", time.gmtime(ts))


def _format_log_line(entry: dict) -> str:
    stamp = time.strftime("%H:%M:%S", time.gmtime(entry["time"]))
    if entry["stream"] == "stderr":
        return f"{stamp} [stderr] {entry['line']}"
    return f"{stamp} {entry['line']}"


# Shown to every visitor, regardless of admin access: describes what
# happened without exposing technical detail (an exit code, in
# particular, is meaningless to most visitors and is exactly the kind of
# thing a real status page keeps out of the public incident feed).
_PUBLIC_INCIDENT_TITLES = {
    "crash_restarting": "Service disruption detected - automatically recovering",
    "crash_no_restart": "Service disruption detected",
    "permanent_failure": "Service is currently unavailable",
    "unresponsive": "Service is responding slowly or not responding - investigating",
    "recovered": "Service has recovered and is operating normally",
    "web_server_down": "Service is currently unavailable",
    "web_server_failed_to_start": "Service is currently unavailable",
}


def _incident_title(inc: dict, admin: bool) -> str:
    if not admin:
        return _PUBLIC_INCIDENT_TITLES.get(inc["event"], "Service disruption detected")
    if inc["event"] == "crash_restarting":
        return f"Crashed with exit code {inc['exit_code']}, restarting automatically"
    if inc["event"] == "crash_no_restart":
        return f"Crashed with exit code {inc['exit_code']}"
    if inc["event"] == "permanent_failure":
        return f"Stopped restarting after repeated crashes (exit code {inc['exit_code']})"
    if inc["event"] == "unresponsive":
        return "No heartbeat received in time - treating as hung, terminating and restarting"
    if inc["event"] == "recovered":
        return "Recovered - no further crashes since, incident closed"
    if inc["event"] == "web_server_down":
        return "Web server thread stopped unexpectedly (not auto-restarted)"
    if inc["event"] == "web_server_failed_to_start":
        return "Web server failed to start"
    return "Service disruption detected"


def snapshot(admin: bool = False, incident_limit: int = None) -> dict:
    """
    Build a JSON-serializable snapshot for the status page's data endpoint:
    overall status, one entry per known bot (plus any extra static entries
    from the process-wide services overrides that don't match a real bot -
    e.g. an external dependency with no supervised process of its own),
    and a merged, most-recent-first incident list.

    The web server is a special case: rather than one row for the whole
    thread, it's normally expanded into one row per currently-registered
    `staypresent.web.*()` route (a status page, a changelog, a JSON
    health check, ...), all sharing that one thread's real, live
    status/uptime/restart data - see `_web_route_service_labels()` above.
    An explicit `services_name` override for it collapses this back down
    to a single named row instead, since a developer who bothered to name
    it themselves is choosing to treat it as one thing.

    Service display names/descriptions come from whatever was last set,
    per key, via staypresent.run()'s own `services_name`/
    `services_description` params, a `bots[i]` entry's own, or a
    staypresent.web.html()/json()/text()/markdown() call (see
    `_global_service_overrides` above) - keyed by the same file/module
    string given to bot_file/
    bot_module/bots[i]['file'/'module'], each value optionally giving
    {"name": ..., "description": ...} to override the auto-derived
    display name/description for that bot. A key that doesn't match any
    actual bot is still included as its own static row (always shown as
    "operational", since StayPresent has no live signal for something it
    isn't itself supervising). These overrides are the same for every
    status page in the process - there's no longer a per-page variant.

    `admin`, when True, includes technical incident detail (the actual
    exit code, and a recent stdout/stderr tail per service) - anyone
    without admin access still sees that an incident happened and its
    current status, just described in plain, non-technical terms.
    Status/uptime/restart counts themselves are the same for everyone
    either way - only the incident detail text and logs differ; nothing
    about a status page's core purpose (showing whether something is up)
    should depend on who's looking at it.

    `incident_limit` caps how many merged incidents are returned (most
    recent first); defaults to _MAX_INCIDENTS_DISPLAYED (the normal
    "recent activity" view). Pass a larger value (up to
    _MAX_INCIDENTS_HISTORY) for the status page's "full history" view.
    """
    with _lock:
        services_override = copy.deepcopy(_global_service_overrides)

    if incident_limit is None:
        incident_limit = _MAX_INCIDENTS_DISPLAYED
    incident_limit = max(0, min(incident_limit, _MAX_INCIDENTS_HISTORY))

    now = time.time()
    with _lock:
        # Built field-by-field rather than one blanket copy.deepcopy(_bots) -
        # that used to deep-copy every bot's full stdout/stderr log buffer
        # (up to _MAX_LOG_LINES_PER_BOT lines each) on every single request,
        # even though a plain (non-admin) visitor's snapshot never uses it
        # at all, and an admin's only ever needs the last
        # _LOG_LINES_IN_SNAPSHOT of them. With the status page polling this
        # every STAYPRESENT_POLL_MS from every open tab, that was real,
        # avoidable work (and lock-held time) paying for data nobody was
        # about to look at.
        bots_copy = {}
        for i, bot in _bots.items():
            entry = {k: v for k, v in bot.items() if k not in ("log", "down_periods", "incidents")}
            # A period's `end` is mutated in place when it closes (see
            # _close_down_period) - copied so a concurrent
            # mark_started()/mark_crashed() elsewhere can't change a
            # value out from under this snapshot mid-computation. Each
            # [start, end] pair is a plain 2-element list of numbers/None
            # (never nested further), so a manual per-pair copy gives the
            # same isolation as copy.deepcopy() at a fraction of the cost -
            # this runs on every snapshot() call (every status-page poll,
            # admin or not), unlike the admin-gated log-buffer copy above.
            entry["down_periods"] = [[start, end] for start, end in bot["down_periods"]]
            # Individual incident dicts are never mutated once appended
            # (_add_incident always inserts a brand-new dict) - only the
            # list itself needs its own copy, to protect against a
            # concurrent insert changing what this snapshot sees
            # mid-iteration; the dicts it points to are safe to share.
            entry["incidents"] = list(bot["incidents"])
            if admin:
                entry["log"] = list(collections.deque(bot["log"], maxlen=_LOG_LINES_IN_SNAPSHOT))
            bots_copy[i] = entry

    matched_keys = set()
    services = []
    all_incidents = []
    overall = "operational"

    for i in sorted(bots_copy):
        bot = bots_copy[i]
        file_key = bot["file_key"]

        # A bot hidden via staypresent.run(status=False) (or its own
        # bots[i]['status']) gets no row, and doesn't contribute to
        # overall_status or the incident feed either - it's still fully
        # supervised (crash/restart handling is untouched), it's just
        # not shown. The web server pseudo-bot (file_key ==
        # WEB_SERVER_FILE_KEY) is handled separately below, since its
        # visibility is normally decided per-route rather than as a
        # single on/off switch.
        if file_key != WEB_SERVER_FILE_KEY and not bot.get("status_visible", True):
            continue

        override = services_override.get(file_key) or {}
        if file_key in services_override:
            matched_keys.add(file_key)

        uptime_pct = _uptime_pct(
            bot, now, bot["first_started_at"],
            extra_down=bot.get("down_before_cutoff", 0.0),
        )
        window_uptimes = {}
        for label, window_seconds in _UPTIME_WINDOWS.items():
            window_start = max(bot["first_started_at"], now - window_seconds)
            window_uptimes[label] = _uptime_pct(bot, now, window_start)

        def _build_service_entry(name: str, description: str) -> dict:
            entry = {
                "name": name,
                "description": description or "",
                "status": bot["state"],
                "uptime": uptime_pct,
                "restarts": bot["restart_count"],
            }
            entry.update(window_uptimes)
            return entry

        # The web server is a single supervised thread, but it's usually
        # serving several independent pages/responses at once (a status
        # page, a changelog, a JSON health check, ...) - a visitor cares
        # whether *each one* is reachable, not just "the web server" as
        # one opaque unit. So, unless a developer explicitly named this
        # whole thing themselves (services_name/services_description -
        # an explicit choice to treat it as one thing), expand it into
        # one row per currently-registered staypresent.web.*() route,
        # all sharing this same bot's real, live status/uptime/restart
        # data - see `_web_route_service_labels()` above. Falls back to
        # a single generic "Web Server" row only when nothing has been
        # registered via staypresent.web.*() at all.
        if file_key == WEB_SERVER_FILE_KEY and not override.get("name"):
            route_labels = _web_route_service_labels()
            if not route_labels:
                # Unlike a real bot, the web server has no single
                # `status=` switch of its own - each
                # staypresent.web.*() call opts its own route in via its
                # own `status=True` (default False). So when nothing has
                # opted in (nothing registered at all, or everything
                # registered is still status=False), there's simply
                # nothing to show for it - no generic "Web Server"
                # fallback row, and (see below) no contribution to
                # overall_status or incidents either. An explicit
                # services_name override (the `not override.get("name")`
                # check above) bypasses all of this, since naming the
                # whole web server yourself is an explicit choice to
                # always show it as one row.
                continue
            first_new_index = len(services)
            for name, description in route_labels:
                services.append(
                    _build_service_entry(name, description or override.get("description") or "")
                )
            representative_name = ", ".join(name for name, _ in route_labels)
            new_indices = range(first_new_index, len(services))
        else:
            # ---> PASS THE BOT ID (i) HERE <---
            name = _display_name(file_key, override, bot.get("display_name"), bot.get("is_module", False), bot_id=i)
            services.append(_build_service_entry(name, override.get("description")))
            representative_name = name
            new_indices = range(len(services) - 1, len(services))

        if _STATE_RANK[bot["state"]] > _STATE_RANK[overall]:
            overall = bot["state"]

        if admin:
            # bots_copy[i]["log"] (built above, under the lock) is already
            # just the tail worth showing, oldest-first - nothing left to
            # slice here. Attached to every row just added for this bot
            # (there's only one underlying log, shared by every route a
            # single web-server thread happens to be expanded into).
            formatted_log = [_format_log_line(entry) for entry in bot["log"]]
            for idx in new_indices:
                services[idx]["log"] = formatted_log

        for inc in bot["incidents"]:
            entry = {
                "title": _incident_title(inc, admin),
                "status": inc["status"],
                "service": representative_name,
                "time": inc["time"],
            }
            # Concrete context beyond the bare exit code (e.g. the actual
            # exception message) - admin-only, and only when something was
            # actually captured for it (a bot that crashes before printing
            # anything has nothing to show here).
            if admin and inc.get("log_line"):
                entry["log_line"] = inc["log_line"]
            all_incidents.append(entry)

    # Extra services declared only via the override dict (no matching bot)
    # - e.g. an external dependency being tracked manually rather than
    # supervised by staypresent.run(). No live signal exists for these, so
    # uptime/restarts are omitted rather than guessed at.
    for file_key, override in services_override.items():
        if file_key in matched_keys:
            continue
        
        status = "operational"
        services.append({
            # ---> NO BOT ID NEEDED HERE (file_key is guaranteed truthy by update_service_override) <---
            "name": _display_name(file_key, override),
            "description": (override or {}).get("description") or "",
            "status": status,
            "uptime": None,
            "restarts": None,
        })

    all_incidents.sort(key=lambda inc: inc["time"], reverse=True)
    total_incidents = len(all_incidents)
    all_incidents = all_incidents[:incident_limit]
    for inc in all_incidents:
        inc["time_display"] = _format_time(inc.pop("time"))

    return {
        "overall_status": overall,
        "services": services,
        "incidents": all_incidents,
        # Lets the status page show/hide a "view full history" control -
        # e.g. if total_incidents > len(incidents), there's more to fetch
        # with a higher incident_limit than what this snapshot returned.
        "total_incidents": total_incidents,
        "generated_at": now,
        "admin": admin,
    }