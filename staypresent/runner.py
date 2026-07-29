import subprocess
import threading
import logging
import signal
import time
import sys
import os

from . import pinger
from .server import app

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
    short_names = [_bot_short_name(cfg) for cfg in bot_configs]
    full_names = [_bot_full_name(cfg) for cfg in bot_configs]
    name_counts = {}
    for name in short_names:
        name_counts[name] = name_counts.get(name, 0) + 1

    labels = []
    for i in range(total):
        display = full_names[i] if name_counts[short_names[i]] > 1 else short_names[i]
        labels.append(f"bot '{display}'" if total == 1 else f"bot[{i}] '{display}'")
    return labels


def _normalize_bot_configs(bot_file, bot_module, bot_args, env, bots):
    """
    Turn the various ways of describing one or more bots into a single,
    uniform list of {"file": str|None, "module": str|None, "args": list,
    "env": dict} dicts. Exactly one of "file"/"module" is set per entry -
    "file" is run as `python <file> ...args`; "module" is run as
    `python -m <module> ...args`, for bots that live inside a package and
    need proper package-relative imports (the same reason `python -m`
    exists in the first place - running a package's module directly as a
    bare script breaks its relative imports).

    Returns the normalized list. Raises TypeError/ValueError on bad input.
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

            configs.append({
                "file": entry_file,
                "module": entry_module,
                "args": list(entry_args),
                "env": dict(entry_env),
            })
        return configs

    if bot_file is not None and bot_module is not None:
        raise TypeError(
            "staypresent.run(): 'bot_file' and 'bot_module' are mutually exclusive - pass "
            "whichever matches how your bot(s) are meant to be launched, not both."
        )
    if bot_file is None and bot_module is None:
        raise TypeError(
            "staypresent.run(): one of 'bot_file' or 'bot_module' is required (pass a single "
            "value, a list of values for multiple bots, or use 'bots' for per-bot args/env)."
        )

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

    # When multiple bots are given via 'bot_file'/'bot_module', the same
    # args/env apply to all of them - use 'bots' instead if each one needs
    # its own.
    shared_args = list(bot_args) if bot_args else []
    shared_env = dict(env) if env else {}
    other_key = "module" if key == "file" else "file"
    return [
        {key: v, other_key: None, "args": list(shared_args), "env": dict(shared_env)}
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
    bot_args: list = None,
    env: dict = None,
    bots: list = None,
    install_signal_handlers: bool = True,
):
    """
    Starts the web server + your bot process(es).

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
            bot: `{"file": "bot.py", "args": [...], "env": {...}}` or
            `{"module": "mypkg.bot", "args": [...], "env": {...}}` - give
            exactly one of `"file"`/`"module"` per entry (`"args"`/`"env"`
            are optional). Mutually exclusive with
            `bot_file`/`bot_module`/`bot_args`/`env`.
        install_signal_handlers: If True (default), StayPresent installs
            its own SIGINT/SIGTERM handlers to gracefully stop the bot
            process(es) and web server on Ctrl+C / a container stop
            signal. Any handler your own script already installed for
            SIGINT/SIGTERM (before calling `run()`) is *chained* - it's
            called after StayPresent's own cleanup runs, so it still fires
            instead of silently being replaced and discarded. Set this to
            False to skip installing StayPresent's handlers entirely and
            take full responsibility for shutdown signaling yourself.
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

    bot_configs = _normalize_bot_configs(bot_file, bot_module, bot_args, env, bots)

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
    if restart_reset_after < 0:
        raise ValueError(
            f"staypresent.run(): restart_reset_after must be >= 0, got {restart_reset_after}."
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

    started_event = threading.Event()
    error_holder = []

    flask_thread = threading.Thread(
        target=_run_server,
        args=(host, port, started_event, error_holder, production, threads),
        daemon=True,
    )
    flask_thread.start()

    # Give the server a brief moment to fail fast (e.g. port already in use)
    # before we launch the bot process(es) alongside it.
    started_event.wait(timeout=1.5)
    if error_holder:
        logger.error("Web server failed to start on %s:%s -> %s", host, port, error_holder[0])
        raise error_holder[0]

    if port == 0:
        logger.info(
            "Web server running on %s (port 0 requested - the OS assigned a free "
            "port; check the server's own startup output above for the actual port).",
            host,
        )
    else:
        logger.info("Web server running on %s:%s", host, port)

    total_bots = len(bot_configs)
    bot_labels = _build_bot_labels(bot_configs)

    def _bot_cmd(cfg):
        if cfg["module"] is not None:
            return [sys.executable, "-m", cfg["module"]] + cfg["args"]
        return [sys.executable, cfg["file"]] + cfg["args"]

    def _bot_env(cfg):
        return {**os.environ, **{k: str(v) for k, v in cfg["env"].items()}} if cfg["env"] else None

    # Holds each bot's current Popen object, keyed by index (or None before
    # its first launch / briefly during a restart). A plain mutable
    # container so `shutdown()` can be registered up front and still always
    # see every bot's live process, even ones (re)launched after it was
    # registered.
    proc_holder = {i: None for i in range(total_bots)}
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
            else:
                logger.error("Web server thread exited unexpectedly.")

    threading.Thread(target=_watch_server_thread, daemon=True).start()

    # Launch every bot's first attempt up front, in the main thread, so a
    # failure to even spawn one (e.g. bad interpreter, out of file
    # descriptors) is raised immediately to the caller - matching the
    # fail-fast behavior of a single bot - rather than surfacing later
    # inside a background thread. If a later bot fails to launch, any
    # already-started bots are terminated first so we don't leak processes.
    initial_processes = {}
    for i, cfg in enumerate(bot_configs):
        try:
            initial_processes[i] = subprocess.Popen(_bot_cmd(cfg), env=_bot_env(cfg))
        except OSError as exc:
            label = bot_labels[i]
            logger.error("Failed to launch %s: %s", label, exc)
            for started in initial_processes.values():
                started.terminate()
            for started in initial_processes.values():
                started.wait()
            raise
        proc_holder[i] = initial_processes[i]

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
                return

            if not restart_on_crash:
                logger.warning("%s exited with code %s. Restarts are disabled.", label, exit_code)
                failures[index] = exit_code
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
                return

            restarts += 1
            logger.warning(
                "%s crashed with code %s. Restarting in %.1fs... (attempt %s/%s)",
                label, exit_code, restart_delay, restarts, max_restarts,
            )
            time.sleep(restart_delay)
            try:
                process = subprocess.Popen(_bot_cmd(cfg), env=_bot_env(cfg))
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
                return
            proc_holder[index] = process
            process_started_at = time.monotonic()

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
        worst_exit_code = next((code for code in failures.values() if code), 1)
        sys.exit(_to_process_exit_code(worst_exit_code))