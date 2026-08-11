"""
StayPresent - Process Runner

Launches and supervises one or more bot processes alongside the web
server: crash detection, auto-restart with backoff, multi-bot
labeling, and graceful SIGINT/SIGTERM shutdown (with signal-handler
chaining so a host script's own handler still runs).

Part of the StayPresent project.
Docs: https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.md
"""

# Created and maintained by Ashish Sharma (Stay Elite).
# Copyright (c) 2026 Ashish Sharma (Stay Elite)
# Licensed under the MIT License. See the LICENSE file for details.

import subprocess
import tempfile
import threading
import logging
import signal
import time
import sys
import os

from . import pinger
from . import status_registry
from .server import app

# Env var name a bot process can read (see heartbeat() below) to find the
# file it should touch periodically to prove it's still alive - only set
# when staypresent.run(heartbeat_timeout=...) is actually used; absent
# otherwise, in which case heartbeat() is a harmless no-op.
_HEARTBEAT_ENV_VAR = "STAYPRESENT_HEARTBEAT_FILE"


def heartbeat() -> None:
    """
    Call this periodically from inside your own bot script to prove to
    StayPresent that it's still alive and doing real work - not just
    still running, which a deadlocked/hung process technically still is.

    Only meaningful when the parent staypresent.run() call was given
    heartbeat_timeout=<seconds>: if your bot goes longer than that
    without calling this, StayPresent treats it as hung, terminates it,
    and lets its normal crash/restart handling take over. If
    heartbeat_timeout wasn't set, this is a harmless no-op - safe to call
    unconditionally from a bot that might run either standalone or under
    StayPresent.

    Cheap enough to call on every iteration of a bot's main loop; there's
    no need to throttle calls yourself.
    """
    path = os.environ.get(_HEARTBEAT_ENV_VAR)
    if not path:
        return
    try:
        with open(path, "a"):
            pass
        os.utime(path, None)
    except OSError:
        # Best-effort - a bot shouldn't crash because its own liveness
        # signal couldn't be written (e.g. temp dir briefly unwritable).
        pass

# run() uses a shared, module-level Flask app (staypresent.server.app),
# so a second call in the same process would just try to bind the exact
# same host:port a second time - which fails, but only with a generic OS-
# level "address already in use" error that gives no hint about *why*.
# This guard turns that into an explicit, specific error at the point of
# the mistake instead.
_run_lock = threading.Lock()
_run_called = False

logger = logging.getLogger("staypresent")
logger.setLevel(logging.INFO)
if not logger.handlers:
    # Attach our own handler to the "staypresent" logger only, instead of
    # calling logging.basicConfig() (which configures the *root* logger).
    # A library touching the root logger can silently clobber, duplicate,
    # or reformat log output the host script/bot has already set up for
    # its own unrelated loggers.
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
    logger.addHandler(_handler)
    logger.propagate = False


def _pump_output(pipe, stream_name: str, index: int, label: str, echo_to) -> None:
    """
    Runs on its own daemon thread, one per bot process per stream (stdout/
    stderr) - reads that stream line by line for as long as the process is
    alive, forwarding each line to two places:

      1. `echo_to` (the parent process's own stdout/stderr) - so a bot's
         output still shows up live in the console exactly as it did
         before StayPresent captured it (via subprocess.PIPE below),
         instead of going silent from the operator's point of view.
      2. status_registry.append_log() - a bounded per-bot ring buffer the
         status page's admin view reads from (a "last log" tail per
         service, and the last captured line attached to crash
         incidents).

    Two of these run concurrently per bot (one for stdout, one for
    stderr) precisely so reading them can't deadlock: subprocess.PIPE has
    a finite OS pipe buffer, and if only one stream were drained while
    the other filled up unread, that bot's process would eventually block
    trying to write to the full one and hang - both must be drained
    independently and continuously.
    """
    try:
        for line in iter(pipe.readline, ""):
            line = line.rstrip("\n")
            print(f"[{label}] {line}", file=echo_to, flush=True)
            status_registry.append_log(index, stream_name, line)
    except (ValueError, OSError):
        # Pipe closed out from under us (process torn down, interpreter
        # shutting down) - nothing more to read, just stop quietly.
        pass
    finally:
        try:
            pipe.close()
        except OSError:
            pass


def _start_output_pumps(process, index: int, label: str) -> None:
    """Spawns the stdout/stderr reader threads for one freshly-launched
    bot process - see _pump_output() above. Called right after every
    subprocess.Popen() for a bot, both the initial launch and every
    restart, so capture never has a gap while a bot is running."""
    threading.Thread(
        target=_pump_output, args=(process.stdout, "stdout", index, label, sys.stdout),
        daemon=True, name=f"staypresent-bot-{index}-stdout",
    ).start()
    threading.Thread(
        target=_pump_output, args=(process.stderr, "stderr", index, label, sys.stderr),
        daemon=True, name=f"staypresent-bot-{index}-stderr",
    ).start()


def _to_process_exit_code(returncode: int) -> int:
    """
    Normalize a subprocess.Popen.returncode into a value safe to pass to
    sys.exit(). When a process is killed by a signal, Popen reports that as
    a *negative* returncode (e.g. -9 for SIGKILL) rather than the POSIX
    "128 + signal number" convention shells, Docker, and Kubernetes use
    (e.g. 137 for SIGKILL/OOM-kill). Passing a negative number straight to
    sys.exit() doesn't raise that convention either - sys.exit(-9) actually
    exits with 247, not 137 - so tooling matching on the standard codes
    would misread it. This converts -N back to the conventional 128 + N.
    """
    if returncode < 0:
        return 128 - returncode
    return returncode


def _serve_with_waitress(host: str, port: int, threads: int) -> bool:
    """
    Try to serve the app with waitress, a production-grade WSGI server.
    Returns True if waitress was available and used, False if it isn't installed.
    """
    try:
        from waitress import serve as waitress_serve
    except ImportError:
        return False

    logger.info(
        "Using waitress (production WSGI server) on %s:%s with %s thread(s)",
        host, port, threads,
    )
    waitress_serve(app, host=host, port=port, threads=threads)
    return True


def _run_server(
    host: str,
    port: int,
    started_event: threading.Event,
    error_holder: list,
    production: bool = True,
    threads: int = 4,
):
    try:
        if production:
            used_waitress = _serve_with_waitress(host, port, threads)
            if used_waitress:
                return

            threads_note = (
                f" Note: threads={threads} has no effect on this fallback server - "
                "Flask's development server doesn't use a thread-pool size."
                if threads != 4
                else ""
            )
            logger.warning(
                "waitress is not installed, falling back to Flask's built-in "
                "development server (not recommended for production). "
                "Install it with `pip install waitress` or `pip install staypresent[prod]` "
                "to silence this warning, or pass staypresent.run(..., production=False) "
                "to use the dev server intentionally.%s",
                threads_note,
            )
        elif threads != 4:
            # threads= only ever does anything when waitress actually ends
            # up serving the app (production=True and waitress installed).
            # With production=False, Flask's own dev server is always used
            # instead, and it silently ignores threads= entirely - so a
            # non-default value here would otherwise look like it's doing
            # something when it isn't.
            logger.warning(
                "staypresent.run(): threads=%s has no effect because production=False - "
                "Flask's development server doesn't use a thread-pool size. This only "
                "applies when production=True and waitress is installed.",
                threads,
            )

        app.run(host=host, port=port, threaded=True)
    except OSError as exc:
        # e.g. "Address already in use" - surface it instead of dying silently
        logger.error("Web server thread failed: %s", exc)
        error_holder.append(exc)
    except Exception as exc:  # noqa: BLE001 - surface any other startup failure too
        # e.g. bad host, waitress raising something other than OSError, etc.
        # Without this, a failure here would just make the thread die silently
        # and the bot would run with no working web server and no explanation.
        logger.error("Web server thread failed: %s", exc)
        error_holder.append(exc)
    finally:
        started_event.set()


def _bot_short_name(cfg: dict) -> str:
    """The concise, human-friendly identifier for a bot: a script's filename, or a module's dotted name as-is (it has no directory prefix to strip)."""
    return os.path.basename(cfg["file"]) if cfg.get("file") else cfg["module"]


def _bot_full_name(cfg: dict) -> str:
    """The fully-disambiguating identifier for a bot: a script's full path, or a module's dotted name (same as the short name - a module name is already fully qualified, there's nothing more specific to fall back to)."""
    return cfg["file"] if cfg.get("file") else cfg["module"]


def _disambiguated_bot_names(bot_configs: list) -> list:
    """
    One display name per bot in `bot_configs`: normally just its short name
    (a script's filename, or a module's dotted name), but promoted to the
    fully-disambiguating name (full file path) for every bot whose short
    name collides with another bot's in this same run - e.g.
    "shard_a/bot.py" and "shard_b/bot.py" both launched via
    `staypresent.run(["shard_a/bot.py", "shard_b/bot.py"])` would otherwise
    both be indistinguishable as just "bot.py". Shared by `_build_bot_labels()`
    (log lines) and `status_registry.reset()` (the status page's default
    service names), so a bot is identified the same way in both places.
    """
    short_names = [_bot_short_name(cfg) for cfg in bot_configs]
    full_names = [_bot_full_name(cfg) for cfg in bot_configs]
    name_counts = {}
    for name in short_names:
        name_counts[name] = name_counts.get(name, 0) + 1
    return [
        full_names[i] if name_counts[short_names[i]] > 1 else short_names[i]
        for i in range(len(bot_configs))
    ]


def _build_bot_labels(bot_configs: list) -> list:
    """
    Build a display label for every bot in bot_configs, used consistently
    in every log line about that bot (startup failures, crashes, restarts,
    giving up).

    Normally this is just the bot's filename, e.g. "bot 'worker.py'" (or
    "bot[i] 'worker.py'" when there's more than one bot), or a module's
    dotted name for module-based bots (e.g. "bot 'mypkg.worker'"). But when
    two or more bots in the same run share the same short name - e.g.
    "shard_a/bot.py" and "shard_b/bot.py" both launched via
    `staypresent.run(["shard_a/bot.py", "shard_b/bot.py"])` - using just the
    filename for those would make otherwise-distinct bots indistinguishable
    in the logs (e.g. two lines both reading "bot[0] 'bot.py' crashed" /
    "bot[1] 'bot.py' crashed", forcing you to cross-reference your own list
    order to know which is which). Whenever a short name collides with
    another bot's, every bot sharing that name is labeled with its fully
    disambiguating name instead (full file path for scripts; for modules,
    the dotted name is already as specific as it gets), so log lines stay
    unambiguous without changing anything for bots that don't collide with
    anything.
    """
    total = len(bot_configs)
    display_names = _disambiguated_bot_names(bot_configs)
    return [
        f"bot '{display}'" if total == 1 else f"bot[{i}] '{display}'"
        for i, display in enumerate(display_names)
    ]


def _validate_env_keys(env_dict: dict, label: str) -> None:
    """
    Every key in an `env` dict is ultimately handed to `subprocess.Popen(env=...)`,
    which requires plain string keys (and `_bot_env()` below already
    stringifies the *values* for exactly this reason) - but a non-str key was
    never checked here, so it surfaced only once the bot process actually
    tried to launch, as a bare `TypeError: expected str, bytes or
    os.PathLike object, not int` from deep inside the subprocess/os
    internals, with nothing pointing back at the real cause. Checked up
    front instead, alongside every other bot-config validation in this
    function, with a message that actually names the offending key and
    where it came from.
    """
    for k in env_dict:
        if not isinstance(k, str):
            raise TypeError(
                f"staypresent.run(): every key in {label} must be a str, got "
                f"{type(k).__name__} ({k!r})."
            )


def _normalize_bot_configs(bot_file, bot_module, bot_args, env, bots, web_server):
    """
    Turn the various ways of describing one or more bots into a single,
    uniform list of {"file": str|None, "module": str|None, "args": list,
    "env": dict} dicts. Exactly one of "file"/"module" is set per entry -
    "file" is run as `python <file> ...args`; "module" is run as
    `python -m <module> ...args`, for bots that live inside a package and
    need proper package-relative imports (the same reason `python -m`
    exists in the first place - running a package's module directly as a
    bare script breaks its relative imports).

    Returns the normalized list, which may be empty - `bot_file`,
    `bot_module`, and `bots` are all optional as long as `web_server` is
    True: that combination means "run the web server only, no bot(s)",
    which is exactly as valid a use of `run()` as "bot(s), no web server"
    (`web_server=False`) is. What's invalid is neither: nothing to
    supervise and nothing to serve is never a sensible call, so that
    specific combination still raises below.

    Raises TypeError/ValueError on bad input.
    """
    if bots is not None:
        if bot_file is not None or bot_module is not None or bot_args is not None or env is not None:
            raise TypeError(
                "staypresent.run(): pass bot files via either 'bot_file'/'bot_module' "
                "(+ optional 'bot_args'/'env' shared by all bots) or 'bots' (per-bot "
                "config), not both."
            )
        if not isinstance(bots, (list, tuple)) or not bots:
            raise TypeError(
                f"staypresent.run(): 'bots' must be a non-empty list of dicts, got {type(bots).__name__}."
            )

        configs = []
        for i, entry in enumerate(bots):
            if not isinstance(entry, dict):
                raise TypeError(f"staypresent.run(): bots[{i}] must be a dict, got {type(entry).__name__}.")

            entry_file = entry.get("file")
            entry_module = entry.get("module")
            if entry_file is not None and entry_module is not None:
                raise TypeError(
                    f"staypresent.run(): bots[{i}] has both 'file' and 'module' set - "
                    "give exactly one."
                )
            if entry_file is None and entry_module is None:
                raise TypeError(f"staypresent.run(): bots[{i}] must set either 'file' or 'module'.")
            if entry_file is not None and (not isinstance(entry_file, str) or not entry_file):
                raise TypeError(f"staypresent.run(): bots[{i}]['file'] must be a non-empty str.")
            if entry_module is not None and (not isinstance(entry_module, str) or not entry_module):
                raise TypeError(f"staypresent.run(): bots[{i}]['module'] must be a non-empty str.")

            entry_args = entry.get("args") or []
            if isinstance(entry_args, str):
                raise TypeError(
                    f"staypresent.run(): bots[{i}]['args'] must be a list of strings, not a bare "
                    f'string. Did you mean bots[{i}]["args"]=["{entry_args}"]?'
                )
            if not isinstance(entry_args, (list, tuple)):
                raise TypeError(
                    f"staypresent.run(): bots[{i}]['args'] must be a list, got {type(entry_args).__name__}."
                )

            entry_env = entry.get("env") or {}
            if not isinstance(entry_env, dict):
                raise TypeError(
                    f"staypresent.run(): bots[{i}]['env'] must be a dict, got {type(entry_env).__name__}."
                )
            _validate_env_keys(entry_env, f"bots[{i}]['env']")

            entry_services_name = entry.get("services_name")
            entry_services_description = entry.get("services_description")
            for pname, pval in (
                ("services_name", entry_services_name),
                ("services_description", entry_services_description),
            ):
                if pval is not None and not isinstance(pval, str):
                    raise TypeError(
                        f"staypresent.run(): bots[{i}]['{pname}'] must be a str or None, "
                        f"got {type(pval).__name__}."
                    )

            # Per-bot status-page visibility override - same "None means
            # not set here, fall back to run()'s own `status=`" resolution
            # `services_name`/`services_description` already use above,
            # applied in run() itself once the final bot list is known.
            entry_status = entry.get("status")
            if entry_status is not None and not isinstance(entry_status, bool):
                raise TypeError(
                    f"staypresent.run(): bots[{i}]['status'] must be a bool or None, "
                    f"got {type(entry_status).__name__}."
                )

            configs.append({
                "file": entry_file,
                "module": entry_module,
                "args": list(entry_args),
                "env": dict(entry_env),
                "services_name": entry_services_name,
                "services_description": entry_services_description,
                "status": entry_status,
            })
        return configs

    if bot_file is not None and bot_module is not None:
        raise TypeError(
            "staypresent.run(): 'bot_file' and 'bot_module' are mutually exclusive - pass "
            "whichever matches how your bot(s) are meant to be launched, not both."
        )
    if bot_file is None and bot_module is None:
        if not web_server:
            raise TypeError(
                "staypresent.run(): nothing to do - no bot(s) given ('bot_file'/'bot_module'/"
                "'bots' are all unset) and web_server=False. Give at least one bot, leave "
                "web_server=True to run the web server on its own, or both."
            )
        return []

    if bot_module is not None:
        key = "module"
        param_name = "bot_module"
        raw = bot_module
    else:
        key = "file"
        param_name = "bot_file"
        raw = bot_file

    values = [raw] if isinstance(raw, str) else raw
    if not isinstance(values, (list, tuple)) or not values:
        raise TypeError(
            f"staypresent.run(): '{param_name}' must be a str or a non-empty list of strings, "
            f"got {type(raw).__name__}."
        )
    for v in values:
        if not isinstance(v, str):
            raise TypeError(
                f"staypresent.run(): every entry in '{param_name}' must be a str, got {type(v).__name__}."
            )

    if bot_args is not None and isinstance(bot_args, str):
        # A very easy mistake to make - list("--flag") silently explodes into
        # ['-', '-', 'f', 'l', 'a', 'g'] instead of raising anything, so the
        # bot process gets launched with garbage argv and no indication why.
        raise TypeError(
            "staypresent.run(): bot_args must be a list of strings, not a bare string. "
            f'Did you mean bot_args=["{bot_args}"]?'
        )
    if bot_args is not None and not isinstance(bot_args, (list, tuple)):
        raise TypeError(f"staypresent.run(): bot_args must be a list, got {type(bot_args).__name__}.")
    if env is not None and not isinstance(env, dict):
        raise TypeError(f"staypresent.run(): env must be a dict, got {type(env).__name__}.")
    if env is not None:
        _validate_env_keys(env, "env")

    # When multiple bots are given via 'bot_file'/'bot_module', the same
    # args/env apply to all of them - use 'bots' instead if each one needs
    # its own.
    shared_args = list(bot_args) if bot_args else []
    shared_env = dict(env) if env else {}
    other_key = "module" if key == "file" else "file"
    return [
        {
            key: v,
            other_key: None,
            "args": list(shared_args),
            "env": dict(shared_env),
            "services_name": None,
            "services_description": None,
            "status": None,
        }
        for v in values
    ]


def run(
    bot_file=None,
    bot_module=None,
    host: str = "0.0.0.0",
    port: int = 8080,
    production: bool = True,
    threads: int = 4,
    restart_on_crash: bool = True,
    max_restarts: int = 5,
    restart_delay: float = 2.0,
    restart_reset_after: float = 60.0,
    heartbeat_timeout: float = None,
    bot_args: list = None,
    env: dict = None,
    bots: list = None,
    install_signal_handlers: bool = True,
    web_server: bool = True,
    services_name: str = None,
    services_description: str = None,
    status: bool = True,
):
    """
    Starts the web server, your bot process(es), or both - whichever you
    ask for. At least one of the two has to be actually happening (running
    with no bots AND web_server=False is rejected, since that would do
    nothing at all), but either one alone is a fully supported way to call
    this.

    Example (single bot):
        staypresent.run("bot.py")
        staypresent.run("bot.py", host="0.0.0.0", port=5000)

    Example (multiple bots, sharing the same args/env):
        staypresent.run(["telegram_bot.py", "discord_bot.py"])

    Example (a bot that's a module inside a package, e.g. runs via
    `python -m mypkg.bot` because it uses package-relative imports):
        staypresent.run(bot_module="mypkg.bot")

    Example (multiple bots, each with its own args/env, mixing scripts and modules):
        staypresent.run(bots=[
            {"file": "telegram_bot.py", "args": ["--verbose"]},
            {"module": "discord_bot.worker", "env": {"SHARD": "0"}},
        ])

    Example (web server only, no bot - e.g. hosting just a status/health
    page with nothing for StayPresent itself to supervise):
        staypresent.run()

    Example (bot only, no web server - e.g. a worker process that doesn't
    need to expose an HTTP port at all, just StayPresent's crash/restart
    supervision):
        staypresent.run("worker.py", web_server=False)

    By default, if the optional `waitress` package is installed, it is used
    to serve the app so you don't see Flask's "development server" warning.
    If `waitress` isn't installed, StayPresent automatically falls back to
    Flask's built-in dev server and logs a one-time warning explaining how
    to fix it.

    If a bot process crashes (exits with a non-zero code), StayPresent will
    automatically restart it, up to `max_restarts` times, waiting
    `restart_delay` seconds between attempts. A clean exit (exit code 0) is
    treated as intentional and is not restarted. Each bot is monitored and
    restarted independently, so one bot crashing/restarting doesn't affect
    the others. Restarts do not apply when you stop StayPresent yourself
    (Ctrl+C / SIGTERM).

    If any bot ultimately fails to stay up - either `restart_on_crash` is
    False and it exits non-zero, or `max_restarts` is exhausted for it -
    this function waits for every other bot to finish as well, then calls
    `sys.exit()` with a non-zero exit code instead of returning normally.
    This makes sure the wrapping process itself exits non-zero, so a
    hosting platform's own restart-on-crash policy (Render, Railway,
    Docker, systemd, etc.) can kick in as a last resort; otherwise the
    process would exit 0 looking "successful" despite a bot having failed.

    Args:
        bot_file: Path to the Python script to run alongside the server, or
            a list of paths to run several bots at once. Launched as
            `python <file> ...`. Mutually exclusive with `bot_module` and
            with `bots` (use `bots` instead if each bot needs its own
            `bot_args`/`env`, or needs a mix of files and modules).
            Optional as long as `web_server` is True - omit `bot_file`,
            `bot_module`, and `bots` entirely to run the web server with no
            bot at all.
        bot_module: Dotted module path (e.g. "mypkg.bot") to run instead of
            a bare script, or a list of such module paths to run several at
            once. Launched as `python -m <module> ...`, exactly like
            running it from the command line yourself. Use this instead of
            `bot_file` whenever your bot lives inside a package and relies
            on package-relative imports (`from . import something`) or
            other behavior that depends on being run as a module rather
            than a standalone script - running it via `bot_file` in that
            case fails with `ImportError: attempted relative import with
            no known parent package`, the same way `python bot.py` would
            from the command line. Unlike `bot_file`, module paths aren't
            checked for existence up front (doing so safely would require
            importing them, which this function deliberately avoids as a
            side effect) - a nonexistent module surfaces as that bot
            process exiting non-zero, handled by the normal crash/restart
            logic below. Mutually exclusive with `bot_file` and `bots`.
        host: Host to bind the web server to.
        port: Port to bind the web server to.
        production: If True (default), use waitress when available for a
            production-ready server. Set to False to force Flask's dev
            server even if waitress is installed.
        threads: Number of worker threads for waitress to use (default 4,
            same as waitress's own default). Only applies when waitress is
            actually used (i.e. `production=True` and waitress installed).
            Increase this if you're pointing real traffic at the server,
            not just occasional keep-alive pings.
        restart_on_crash: If True (default), automatically relaunch a bot
            process if it exits with a non-zero exit code. Set to False to
            keep the old behavior of exiting once a bot process ends.
        max_restarts: Maximum number of times to restart a bot process
            after a crash before giving up. Ignored if restart_on_crash is
            False. Applies per bot when running multiple.
        restart_delay: Seconds to wait before relaunching a bot process
            after a crash. Ignored if restart_on_crash is False.
        restart_reset_after: If a bot stays up for at least this many
            seconds after a restart, its restart counter is reset to 0.
            This makes `max_restarts` a "consecutive crashes" budget
            instead of a lifetime one, so a bot that runs fine for a long
            time and then crashes once isn't penalized for earlier,
            unrelated crashes. Ignored if restart_on_crash is False.
        heartbeat_timeout: Optional. If given (seconds), StayPresent
            additionally detects a *hung* bot - one whose process is
            still running but has stopped doing anything (deadlocked,
            stuck in an infinite loop, blocked forever on I/O) - which
            exit-code-based crash detection can never catch on its own,
            since a hung process never exits. Requires your bot to call
            `staypresent.heartbeat()` periodically (e.g. once per loop
            iteration); if it goes longer than `heartbeat_timeout`
            seconds without doing so, StayPresent logs a "possibly hung"
            incident, terminates the process, and lets the normal
            crash/restart handling above take over. Left as None
            (default) means no such check runs at all - a bot that never
            calls `heartbeat()` is not penalized unless this is set.
        bot_args: Optional list of extra command-line arguments to pass to
            every bot in `bot_file`/`bot_module` (e.g. `["--verbose"]`).
            Ignored/invalid when `bots` is used - put per-bot args in each
            bot's dict there instead.
        env: Optional dict of extra environment variables for every bot in
            `bot_file`/`bot_module`. Merged on top of the current process's
            environment (i.e. you only need to specify what you want to
            add/override). Ignored/invalid when `bots` is used - put
            per-bot env in each bot's dict there instead.
        bots: Optional list of dicts for per-bot configuration, one dict per
            bot: `{"file": "bot.py", "args": [...], "env": {...},
            "services_name": "Bot A", "services_description": "...",
            "status": True}` or the `"module"` equivalent - give exactly
            one of `"file"`/`"module"` per entry (`"args"`/`"env"`/
            `"services_name"`/`"services_description"`/`"status"` are all
            optional). `"services_name"`/`"services_description"` set that
            one bot's status-page display name/description directly (same
            effect as this function's own `services_name`/
            `services_description`, but scoped to a single entry here
            instead of requiring exactly one bot process-wide - this is
            the way to tag bots individually when there's more than one).
            `"status"`, if set, overrides this function's own `status=`
            just for that one bot - e.g.
            `bots=[{"file": "a.py"}, {"file": "b.py", "status": False}]`
            keeps bot A visible on the status page (the default) while
            hiding bot B from it. Mutually exclusive with `bot_file`/
            `bot_module`/`bot_args`/`env`.
        install_signal_handlers: If True (default), StayPresent installs
            its own SIGINT/SIGTERM handlers to gracefully stop the bot
            process(es) and web server on Ctrl+C / a container stop
            signal. Any handler your own script already installed for
            SIGINT/SIGTERM (before calling `run()`) is *chained* - it's
            called after StayPresent's own cleanup runs, so it still fires
            instead of silently being replaced and discarded. Set this to
            False to skip installing StayPresent's handlers entirely and
            take full responsibility for shutdown signaling yourself.
        web_server: If True (default), start the background web server.
            Set to False to run only your bot(s) - StayPresent's crash
            detection, auto-restart, and multi-bot supervision all still
            apply, there's just no HTTP server at all (`host`/`port`/
            `production`/`threads` are ignored, and every `staypresent.web`
            registration is inert, since nothing is listening to serve it).
            Requires at least one bot (`bot_file`/`bot_module`/`bots`) -
            `web_server=False` with no bot configured either would do
            nothing at all, so that combination raises `TypeError`.
        services_name: Optional display name to use, on the status page,
            for the one bot this call configures - instead of the default
            "run() with multiple bots" combination requires (see below).
            When `web_server=True` (the default) and no bot is configured
            at all, this instead renames the web server's own row (whose
            key is `"web_server"`). Same last-call-wins behavior as the
            `staypresent.web.html()`/`json()`/`text()`/`markdown()`
            functions' own `services_name` - whichever of those or this
            is called last for the same target wins outright; a call
            here left unset (the default) never overwrites one already
            made via one of those.

            Only valid with zero or one bot configured (a single
            `bot_file`/`bot_module` string, or `bots` with exactly one
            entry) - raises `TypeError` with more than one, since a
            single string can't unambiguously name any one of several
            bots. Tag each bot individually in that case instead, via
            `bots=[{"file": "a.py", "services_name": "Bot A"}, {"file":
            "b.py", "services_name": "Bot B"}]` (each entry's own
            `services_name`/`services_description` keys, both optional).
        services_description: Optional description shown under that same
            row's name on the status page. Same single-bot-only rule,
            per-bot `bots[i]['services_description']` alternative for
            multiple bots, and last-call-wins behavior as `services_name`
            above.
        status: Whether the bot(s)/worker process(es) this call configures
            get their own row on the status page at all. Defaults to True
            - shown unless you explicitly turn it off. Set to False to
            supervise a bot exactly as normal (crash detection, auto-
            restart, everything) while keeping it off the status page
            entirely - e.g. an internal worker nobody outside the team
            needs to see. Applies to every bot this call configures;
            override it for one bot at a time instead via that bot's own
            `bots=[{"file": "a.py", "status": False}, ...]` entry, which
            takes priority over this. Has no effect on the web server's
            own row - see `staypresent.web.*()`'s own `status=` param for
            that (opt-in per route, defaulting to False).
    """

    global _run_called
    # Peek (without claiming) so a second call fails fast with the real
    # "already called" error rather than that error being masked by
    # whatever validation error happens to run first below.
    if _run_called:
        raise RuntimeError(
            "staypresent.run() was already called once in this process. It uses a "
            "single shared, module-level web server, so calling it again would just "
            "try to bind the same host:port a second time and fail with a generic "
            "'address already in use' error. If you meant to run multiple bots, pass "
            "them all to a single run() call instead (bot_file=['a.py', 'b.py'], or "
            "bots=[{'file': 'a.py'}, {'file': 'b.py'}])."
        )

    bot_configs = _normalize_bot_configs(bot_file, bot_module, bot_args, env, bots, web_server)

    if not bot_configs and (bot_args is not None or env is not None):
        # Reachable when web_server=True (the default) and no bot_file/
        # bot_module/bots was given either - a valid, supported call
        # ("web server only", see _normalize_bot_configs above), but
        # bot_args/env only ever apply to a bot process StayPresent
        # itself launches. With no bot configured at all, there's nothing
        # to pass them to, so they were previously accepted and silently
        # discarded - easy to mistake for "it'll apply once I add a bot
        # later" or simply not notice at all. Mirrors the analogous
        # host/port/production/threads warning below for the opposite
        # case (bot(s) but no web server).
        logger.warning(
            "staypresent.run(): 'bot_args'/'env' were given but no bot ('bot_file'/"
            "'bot_module'/'bots') was configured, so they have no effect."
        )

    for cfg in bot_configs:
        if cfg["file"] is not None and not os.path.isfile(cfg["file"]):
            raise FileNotFoundError(
                f"staypresent.run(): bot file '{cfg['file']}' does not exist or is not a file."
            )

    if not (0 <= port <= 65535):
        raise ValueError(f"staypresent.run(): port must be between 0 and 65535, got {port}.")
    if threads < 1:
        # threads=0 doesn't error out anywhere - waitress just accepts
        # connections and never services them, so the server looks "up"
        # (health checks on the TCP level pass) but every request hangs
        # forever. That silent failure is worse than refusing outright.
        raise ValueError(f"staypresent.run(): threads must be at least 1, got {threads}.")
    if max_restarts < 0:
        raise ValueError(f"staypresent.run(): max_restarts must be >= 0, got {max_restarts}.")
    if restart_delay < 0:
        raise ValueError(f"staypresent.run(): restart_delay must be >= 0, got {restart_delay}.")
    # Validated up front (same as the other params above) even though the
    # result isn't actually applied until after status_registry.reset()
    # below - so a bad services_name/services_description raises before
    # _run_called is claimed, instead of leaving the process in a
    # half-started state.
    for _pname, _pval in (("services_name", services_name), ("services_description", services_description)):
        if _pval is not None and not isinstance(_pval, str):
            raise TypeError(
                f"staypresent.run(): '{_pname}' must be a str or None, got {type(_pval).__name__}."
            )
    if (services_name is not None or services_description is not None) and len(bot_configs) > 1:
        raise TypeError(
            "staypresent.run(): 'services_name'/'services_description' only work when "
            "there's exactly one bot (or none) configured - with multiple bots, tag each "
            "one individually instead, e.g. bots=[{'file': 'a.py', 'services_name': "
            "'Bot A'}, {'file': 'b.py', 'services_name': 'Bot B'}]."
        )
    if not isinstance(status, bool):
        raise TypeError(f"staypresent.run(): 'status' must be a bool, got {type(status).__name__}.")
    if restart_reset_after < 0:
        raise ValueError(
            f"staypresent.run(): restart_reset_after must be >= 0, got {restart_reset_after}."
        )
    if heartbeat_timeout is not None and heartbeat_timeout <= 0:
        raise ValueError(
            f"staypresent.run(): heartbeat_timeout must be > 0 (or None to disable), "
            f"got {heartbeat_timeout}."
        )

    # Only now - once every validation above has actually passed and we're
    # committed to starting the shared server - claim the "already called"
    # slot. Claiming it any earlier (e.g. before validation, as before) meant
    # a first call that failed validation (bad port, missing bot file, ...)
    # never started a server at all, yet permanently blocked every
    # subsequent, otherwise-valid call in the same process behind the
    # "already called" error above, masking the real (validation) error on
    # the very next attempt. The lock still makes the check-and-set atomic
    # against a genuinely concurrent second call reaching this point.
    with _run_lock:
        if _run_called:
            raise RuntimeError(
                "staypresent.run() was already called once in this process. It uses a "
                "single shared, module-level web server, so calling it again would just "
                "try to bind the same host:port a second time and fail with a generic "
                "'address already in use' error. If you meant to run multiple bots, pass "
                "them all to a single run() call instead (bot_file=['a.py', 'b.py'], or "
                "bots=[{'file': 'a.py'}, {'file': 'b.py'}])."
            )
        _run_called = True

    # Computed before the server thread starts (not after, as a prior
    # version of this code did) - status_registry.reset() has to happen
    # before the server can possibly receive its first request, or a
    # status page request arriving in that gap would see an empty
    # service list even though bots ARE configured, just not registered
    # yet. bot_labels/total_bots only depend on bot_configs, which is
    # already fully validated by this point, so there's no reason they
    # need to wait until after the server's up anyway.
    total_bots = len(bot_configs)
    bot_labels = _build_bot_labels(bot_configs)
    # Each bot's own bots[i]['services_name'/'services_description'], if
    # given, is applied directly against that bot's own file/module key -
    # independent of whichever bot count this run() call ends up with, so
    # this can happen before reset() below.
    for cfg in bot_configs:
        per_bot_name = cfg.get("services_name")
        per_bot_description = cfg.get("services_description")
        if per_bot_name is not None or per_bot_description is not None:
            status_registry.update_service_override(
                cfg["file"] or cfg["module"],
                per_bot_name,
                per_bot_description,
                caller="staypresent.run() (bots[i])",
            )
    # This function's own services_name/services_description (a plain
    # str) can't resolve to a real key until reset() below knows the
    # final bot count - staged here, then resolved from inside reset()
    # itself. Only touch the pending slot if run() was actually given one -
    # leaving both unset (the default) must NOT wipe out a pending
    # override already staged by an earlier staypresent.web.html()/json()/
    # text()/markdown() call, which is normally called before run() (run()
    # blocks until shutdown). See set_pending_single_target_override()'s
    # "last call wins outright" docstring.
    if services_name is not None or services_description is not None:
        status_registry.set_pending_single_target_override(
            services_name, services_description, caller="staypresent.run()"
        )
    # Per-bot status-page visibility: a bot's own bots[i]['status'] (if
    # set) wins outright, otherwise it falls back to this call's own
    # `status=` (True by default) - same override-then-fallback pattern
    # bot_labels/services_name already use elsewhere in this function.
    bot_status = [
        cfg["status"] if cfg.get("status") is not None else status
        for cfg in bot_configs
    ]
    status_registry.reset(
        bot_configs,
        _disambiguated_bot_names(bot_configs),
        track_web_server=web_server,
        bot_status=bot_status,
    )
    # The web server thread's own pseudo-bot index in status_registry -
    # only meaningful when web_server=True, but harmless to compute either
    # way (it's simply never looked up when there's no web server to
    # track). Placed right after the last real bot, matching reset()'s own
    # `len(bot_configs)` slot for it.
    web_server_index = total_bots

    if not web_server and (host != "0.0.0.0" or port != 8080 or production is not True or threads != 4):
        logger.warning(
            "staypresent.run(): host/port/production/threads have no effect because "
            "web_server=False - no web server is being started at all."
        )

    flask_thread = None
    if web_server:
        started_event = threading.Event()
        error_holder = []

        flask_thread = threading.Thread(
            target=_run_server,
            args=(host, port, started_event, error_holder, production, threads),
            daemon=True,
        )
        flask_thread.start()

        # Give the server a brief moment to fail fast (e.g. port already in
        # use) before we launch the bot process(es) alongside it.
        started_event.wait(timeout=1.5)
        if error_holder:
            logger.error("Web server failed to start on %s:%s -> %s", host, port, error_holder[0])
            # The status page should reflect this too, not just the log -
            # it's tracked as a bot-like service (see reset() above)
            # precisely so a startup failure here shows up the same way a
            # bot's would, instead of leaving the page silently blind to
            # the fact that there's no web server behind it at all.
            status_registry.mark_web_server_down(
                web_server_index, detail=str(error_holder[0]), failed_to_start=True,
            )
            raise error_holder[0]

        if port == 0:
            logger.info(
                "Web server running on %s (port 0 requested - the OS assigned a free "
                "port; check the server's own startup output above for the actual port).",
                host,
            )
        else:
            logger.info("Web server running on %s:%s", host, port)
    else:
        logger.info("web_server=False - no web server will be started; running bot(s) only.")

    def _bot_env(cfg, extra=None):
        if not cfg["env"] and not extra:
            return None
        merged = {**os.environ, **{k: str(v) for k, v in cfg["env"].items()}}
        if extra:
            merged.update(extra)
        return merged

    def _heartbeat_path(index):
        # Stable per-bot-index path across restarts of the same bot
        # (keyed by this run's own pid so concurrent staypresent.run()
        # processes on the same machine never collide on the same file).
        return os.path.join(tempfile.gettempdir(), f"staypresent-heartbeat-{os.getpid()}-{index}.touch")

    def _touch_heartbeat_file(path):
        # Reset the file's mtime to "now" at the moment a bot (re)starts,
        # so a stale mtime left over from a previous crashed attempt
        # doesn't make the fresh process look hung before it's even had a
        # chance to call heartbeat() once.
        try:
            with open(path, "a"):
                pass
            os.utime(path, None)
        except OSError:
            pass

    def _remove_heartbeat_file(index):
        # The path is stable across restarts of the same bot (see
        # _heartbeat_path above), so it's only ever safe to delete once
        # that bot index is done for good - a clean exit, a crash it won't
        # be restarted from, or giving up after max_restarts. Call this at
        # each of those terminal points (and for every bot on shutdown())
        # so a long-running deploy doesn't leave one
        # staypresent-heartbeat-<pid>-<index>.touch file behind per bot,
        # forever, even after the process exits cleanly.
        if heartbeat_timeout is None:
            return
        try:
            os.remove(_heartbeat_path(index))
        except OSError:
            pass

    def _watch_heartbeat(index, process, heartbeat_path, label):
        # Polls rather than blocking on anything - cheap, and naturally
        # exits on its own once the process it's watching does (via the
        # process.poll() check each iteration), without needing to be
        # told the process died at all.
        check_interval = min(5.0, heartbeat_timeout)
        while True:
            time.sleep(check_interval)
            if stopping.is_set() or process.poll() is not None:
                return
            try:
                last_beat = os.path.getmtime(heartbeat_path)
            except OSError:
                # Shouldn't normally happen (_touch_heartbeat_file creates
                # it up front), but don't false-trigger on a missing file.
                continue
            if time.time() - last_beat > heartbeat_timeout:
                logger.error(
                    "%s has not called staypresent.heartbeat() in over %.0fs - "
                    "treating it as hung, terminating.",
                    label, heartbeat_timeout,
                )
                status_registry.mark_unresponsive(index)
                try:
                    process.terminate()
                except OSError:
                    pass
                return

    def _start_heartbeat_watch(index, process, label):
        if heartbeat_timeout is None:
            return
        path = _heartbeat_path(index)
        _touch_heartbeat_file(path)
        threading.Thread(
            target=_watch_heartbeat, args=(index, process, path, label),
            daemon=True, name=f"staypresent-bot-{index}-heartbeat",
        ).start()

    # One recovery-check "generation" counter per bot: schedule_recovery_
    # check() below stamps each scheduled check with the current value at
    # the moment it's scheduled, then only acts on it if the count is
    # still unchanged restart_reset_after seconds later - so an earlier
    # bot start's stale check can never mark a *later* crash/restart
    # "recovered" out from under it.
    recovery_generation = [0] * total_bots

    def _schedule_recovery_check(index, process):
        recovery_generation[index] += 1
        my_generation = recovery_generation[index]

        def _check():
            if stopping.is_set() or recovery_generation[index] != my_generation:
                return
            if process.poll() is None:
                status_registry.mark_recovered(index)

        timer = threading.Timer(restart_reset_after, _check)
        timer.daemon = True
        timer.start()

    def _bot_cmd(cfg):
        if cfg["module"] is not None:
            return [sys.executable, "-m", cfg["module"]] + cfg["args"]
        return [sys.executable, cfg["file"]] + cfg["args"]

    # Holds each bot's current Popen object, keyed by index (or None before
    # its first launch / briefly during a restart). A plain mutable
    # container so `shutdown()` can be registered up front and still always
    # see every bot's live process, even ones (re)launched after it was
    # registered.
    proc_holder = {i: None for i in range(total_bots)}
    # Guards proc_holder writes (a crash-restart storing its newly spawned
    # Popen) against shutdown()'s read (snapshotting every live process to
    # terminate) - see the restart-delay handling in _manage_bot() below for
    # why this matters.
    proc_lock = threading.Lock()
    stopping = threading.Event()
    failures = {}  # index -> exit code, for bots that ultimately gave up

    # Populated below (before any signal can actually be delivered) with
    # whatever handler was previously installed for SIGINT/SIGTERM, if any
    # - so shutdown() can chain to it instead of silently discarding it.
    previous_handlers = {}

    def shutdown(signum, frame):
        stopping.set()
        try:
            sig_name = signal.Signals(signum).name
        except ValueError:
            sig_name = str(signum)
        logger.info("Received %s, stopping...", sig_name)

        # cron() pingers run on daemon threads that die with the process
        # (sys.exit() below) and aren't otherwise tracked here - this is
        # just a log line for visibility into what was still running, not
        # an attempt to join/stop those threads.
        active_crons = pinger.active_cron_handles()
        if active_crons:
            logger.info(
                "%d cron pinger(s) still running at shutdown: %s",
                len(active_crons),
                ", ".join(h.url for h in active_crons),
            )

        with proc_lock:
            procs = [p for p in proc_holder.values() if p is not None]
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("A bot process did not exit in time, killing it.")
                proc.kill()
                proc.wait()

        # Every bot's heartbeat-watchdog temp file (if any) is done for
        # good once the process is dead and we're not coming back for
        # this run() call - clean them all up rather than leaving them on
        # disk until the OS's own temp-cleanup policy (if any) gets to
        # them.
        for i in range(total_bots):
            _remove_heartbeat_file(i)

        # Chain to whatever handler the host script had already installed
        # for this signal (if any) before we replaced it, so it still runs
        # instead of being silently discarded. signal.signal() returns
        # signal.SIG_DFL/signal.SIG_IGN (not callables) when nothing custom
        # was previously installed - only call through for an actual
        # callable.
        #
        # signal.default_int_handler is *not* a "host script installed
        # this" handler - it's the interpreter's own baseline SIGINT
        # handler (the thing that normally turns Ctrl+C into a
        # KeyboardInterrupt), present by default in every process that
        # hasn't touched SIGINT itself. That's true for the overwhelming
        # majority of scripts calling run(). Chaining to it would raise
        # KeyboardInterrupt right here - a BaseException, not an Exception,
        # so it would skip both `except` clauses below, skip our own
        # `sys.exit(0)`, and blow up whatever thread was interrupted with a
        # raw traceback instead of the graceful shutdown this handler
        # exists to provide. So it's deliberately skipped rather than
        # called through.
        prev = previous_handlers.get(signum)
        if callable(prev) and prev is not signal.default_int_handler:
            try:
                prev(signum, frame)
            except SystemExit:
                raise
            except BaseException:  # noqa: BLE001 - a bad chained handler (even one raising
                # KeyboardInterrupt/another BaseException) must not block our own exit
                logger.exception("Previously-installed %s handler raised an exception.", sig_name)

        sys.exit(0)

    if install_signal_handlers:
        try:
            previous_handlers[signal.SIGINT] = signal.signal(signal.SIGINT, shutdown)
            previous_handlers[signal.SIGTERM] = signal.signal(signal.SIGTERM, shutdown)
        except ValueError:
            # signal handlers can only be registered on the main thread;
            # if run() is called elsewhere, skip graceful signal handling
            # rather than crashing.
            logger.warning(
                "Could not register signal handlers (not running on main thread). "
                "Ctrl+C / SIGTERM will not gracefully stop the bot process(es)."
            )
    else:
        logger.info(
            "install_signal_handlers=False - StayPresent will not install its own "
            "SIGINT/SIGTERM handlers. Your own script is responsible for triggering "
            "shutdown (e.g. terminating bot process(es) yourself)."
        )

    # Watch for the web server thread dying unexpectedly after a successful
    # startup (e.g. waitress hitting an unhandled error mid-run). A crash at
    # startup is already caught above; this catches crashes later on, since
    # otherwise the thread would just silently disappear (it's a daemon
    # thread) and the bot(s) would keep running with no working web server.
    def _watch_server_thread():
        flask_thread.join()
        if not stopping.is_set():
            if error_holder:
                logger.error("Web server stopped unexpectedly: %s", error_holder[-1])
                detail = str(error_holder[-1])
            else:
                logger.error("Web server thread exited unexpectedly.")
                detail = None
            status_registry.mark_web_server_down(web_server_index, detail=detail)

    if flask_thread is not None:
        threading.Thread(target=_watch_server_thread, daemon=True).start()

    # Launch every bot's first attempt up front, in the main thread, so a
    # failure to even spawn one (e.g. bad interpreter, out of file
    # descriptors) is raised immediately to the caller - matching the
    # fail-fast behavior of a single bot - rather than surfacing later
    # inside a background thread. If a later bot fails to launch, any
    # already-started bots are terminated first so we don't leak processes.
    initial_processes = {}
    for i, cfg in enumerate(bot_configs):
        env_extra = None
        if heartbeat_timeout is not None:
            heartbeat_path = _heartbeat_path(i)
            _touch_heartbeat_file(heartbeat_path)
            env_extra = {_HEARTBEAT_ENV_VAR: heartbeat_path}
        try:
            initial_processes[i] = subprocess.Popen(
                _bot_cmd(cfg), env=_bot_env(cfg, env_extra),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
        except OSError as exc:
            label = bot_labels[i]
            logger.error("Failed to launch %s: %s", label, exc)
            for started in initial_processes.values():
                started.terminate()
            for started in initial_processes.values():
                started.wait()
            # This bot (and every other one already launched above) is
            # never coming up in this run() call - remove every heartbeat
            # file already touched for them rather than leaving them
            # behind on disk.
            for cleanup_index in list(initial_processes) + [i]:
                _remove_heartbeat_file(cleanup_index)
            raise
        proc_holder[i] = initial_processes[i]
        _start_output_pumps(initial_processes[i], i, bot_labels[i])
        _start_heartbeat_watch(i, initial_processes[i], bot_labels[i])
        status_registry.mark_started(i)
        _schedule_recovery_check(i, initial_processes[i])

    def _manage_bot(index, cfg, process):
        label = bot_labels[index]
        process_started_at = time.monotonic()
        restarts = 0

        while True:
            process.wait()

            if stopping.is_set():
                # We're shutting down deliberately (signal handler already
                # handles process cleanup + exit), nothing more to do here.
                return

            exit_code = process.returncode
            uptime = time.monotonic() - process_started_at

            if exit_code == 0:
                logger.info("%s exited cleanly (code 0). Not restarting.", label)
                status_registry.mark_clean_exit(index)
                _remove_heartbeat_file(index)
                return

            if not restart_on_crash:
                logger.warning("%s exited with code %s. Restarts are disabled.", label, exit_code)
                failures[index] = exit_code
                status_registry.mark_crashed(index, exit_code, will_restart=False)
                _remove_heartbeat_file(index)
                return

            if uptime >= restart_reset_after and restarts > 0:
                logger.info(
                    "%s had been running for %.0fs, treating this as a fresh crash streak.",
                    label, uptime,
                )
                restarts = 0

            if restarts >= max_restarts:
                logger.error(
                    "%s crashed with code %s. Reached max_restarts (%s), giving up.",
                    label, exit_code, max_restarts,
                )
                failures[index] = exit_code
                status_registry.mark_permanently_failed(index, exit_code)
                _remove_heartbeat_file(index)
                return

            restarts += 1
            logger.warning(
                "%s crashed with code %s. Restarting in %.1fs... (attempt %s/%s)",
                label, exit_code, restart_delay, restarts, max_restarts,
            )
            status_registry.mark_crashed(index, exit_code, will_restart=True)
            # stopping.wait() instead of time.sleep(): time.sleep() cannot be
            # woken up early, so a shutdown signal arriving during this
            # backoff window would sit here for the full restart_delay
            # before this thread ever re-checked `stopping` - and since
            # these monitor threads are non-daemon, the whole process (even
            # after shutdown()'s own sys.exit(0)) would hang until that
            # delay elapsed. stopping.wait(timeout=...) returns immediately
            # (True) the moment shutdown() calls stopping.set(), the same
            # pattern pinger.py's cron loop already uses for its own
            # interval wait.
            if stopping.wait(timeout=restart_delay):
                return
            with proc_lock:
                # Re-check while holding the same lock shutdown() uses to
                # snapshot proc_holder for termination. Without this,
                # `stopping` could still flip to set() in the narrow gap
                # between the wait() above returning and this line - the
                # lock (not the flag alone) is what actually closes that
                # window: either shutdown() takes the lock first (sees
                # nothing new to terminate here, since this process doesn't
                # exist yet) and this thread then sees `stopping` set and
                # returns without spawning, or this thread takes the lock
                # first (spawns and records the process) and shutdown() then
                # sees - and terminates - it in its own snapshot. Either
                # ordering is safe; only "spawn now, be discovered by
                # shutdown() never" is not, and this lock rules that out.
                if stopping.is_set():
                    return
                env_extra = None
                if heartbeat_timeout is not None:
                    heartbeat_path = _heartbeat_path(index)
                    _touch_heartbeat_file(heartbeat_path)
                    env_extra = {_HEARTBEAT_ENV_VAR: heartbeat_path}
                try:
                    process = subprocess.Popen(
                        _bot_cmd(cfg), env=_bot_env(cfg, env_extra),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, bufsize=1,
                    )
                except OSError as exc:
                    # The OS itself refused to spawn the process (out of file
                    # descriptors/memory, a process-count ulimit, etc) - this is
                    # distinct from the bot starting and then crashing, which is
                    # handled above. Give up cleanly with a clear log message
                    # instead of letting this exception escape unhandled and
                    # take down this bot's monitor thread with a raw traceback.
                    logger.error(
                        "Failed to relaunch %s after crash (attempt %s/%s): %s. Giving up.",
                        label, restarts, max_restarts, exc,
                    )
                    failures[index] = 1
                    status_registry.mark_permanently_failed(index, 1)
                    _remove_heartbeat_file(index)
                    return
                proc_holder[index] = process
                _start_output_pumps(process, index, label)
                _start_heartbeat_watch(index, process, label)
            process_started_at = time.monotonic()
            status_registry.mark_started(index)
            _schedule_recovery_check(index, process)

    if total_bots == 0:
        # No bots configured (web_server=True is guaranteed here - the
        # alternative was already rejected in _normalize_bot_configs).
        # There's nothing to hand to monitor_threads below - joining an
        # empty list returns immediately - so without this, run() would
        # just return right after starting the server, and since
        # flask_thread is itself a daemon thread, the whole process would
        # then exit immediately behind it instead of actually staying up.
        # Blocking on the server thread directly keeps the process alive
        # the same way joining bot monitor threads normally would, and is
        # interrupted the same way too: shutdown()'s sys.exit(0) raises
        # SystemExit right here when a signal arrives.
        flask_thread.join()
        if stopping.is_set():
            # shutdown() already handled cleanup + process exit.
            return
        # The server thread ended on its own, without a shutdown signal -
        # i.e. it crashed after a successful startup (already logged by
        # _watch_server_thread above). Exit non-zero so a hosting
        # platform's own restart policy notices, the same reasoning the
        # bot-failure path below already applies.
        sys.exit(1)

    monitor_threads = [
        threading.Thread(
            target=_manage_bot,
            args=(i, cfg, initial_processes[i]),
            daemon=False,
            name=f"staypresent-bot-{i}",
        )
        for i, cfg in enumerate(bot_configs)
    ]
    for t in monitor_threads:
        t.start()
    for t in monitor_threads:
        t.join()

    if stopping.is_set():
        # shutdown() already handled process cleanup + process exit.
        return

    if failures:
        failed_labels = ", ".join(bot_labels[i] for i in sorted(failures))
        logger.error(
            "%d of %d bot process(es) failed to stay up: %s",
            len(failures), total_bots, failed_labels,
        )
        # Sorted by index (same order as failed_labels above) rather than
        # dict insertion order: failures[index] is written by each bot's own
        # monitor thread as it gives up, so insertion order reflects the
        # essentially-random order those threads happen to finish in, not
        # anything meaningful about severity. Without sorting, run()'s own
        # final exit code could silently differ between two otherwise-
        # identical runs (same bots, same failures) purely based on thread
        # scheduling - sorting makes it deterministic: the lowest-indexed
        # failing bot's exit code is used every time.
        worst_exit_code = next((failures[i] for i in sorted(failures) if failures[i]), 1)
        sys.exit(_to_process_exit_code(worst_exit_code))