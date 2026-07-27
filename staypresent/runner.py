import subprocess
import threading
import logging
import signal
import time
import sys
import os

from .server import app

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
    
    if returncode < 0:
        return 128 - returncode
    return returncode


def _serve_with_waitress(host: str, port: int, threads: int) -> bool:
    
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

            logger.warning(
                "waitress is not installed, falling back to Flask's built-in "
                "development server (not recommended for production). "
                "Install it with `pip install waitress` or `pip install staypresent[prod]` "
                "to silence this warning, or pass staypresent.run(..., production=False) "
                "to use the dev server intentionally."
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


def _bot_label(index: int, file_path: str, total: int) -> str:
    name = os.path.basename(file_path)
    return f"bot '{name}'" if total == 1 else f"bot[{index}] '{name}'"


def _normalize_bot_configs(bot_file, bot_args, env, bots):
    
    if bots is not None:
        if bot_file is not None or bot_args is not None or env is not None:
            raise TypeError(
                "staypresent.run(): pass bot files via either 'bot_file' (+ optional "
                "'bot_args'/'env' shared by all bots) or 'bots' (per-bot config), not both."
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
            if not isinstance(entry_file, str) or not entry_file:
                raise TypeError(f"staypresent.run(): bots[{i}]['file'] must be a non-empty str.")

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

            configs.append({"file": entry_file, "args": list(entry_args), "env": dict(entry_env)})
        return configs

    if bot_file is None:
        raise TypeError(
            "staypresent.run(): 'bot_file' is required (pass a single path, a list of paths "
            "for multiple bots, or use 'bots' for per-bot args/env)."
        )

    files = [bot_file] if isinstance(bot_file, str) else bot_file
    if not isinstance(files, (list, tuple)) or not files:
        raise TypeError(
            f"staypresent.run(): 'bot_file' must be a str or a non-empty list of strings, "
            f"got {type(bot_file).__name__}."
        )
    for f in files:
        if not isinstance(f, str):
            raise TypeError(f"staypresent.run(): every entry in 'bot_file' must be a str, got {type(f).__name__}.")

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

    # When multiple bot files are given via 'bot_file', the same args/env
    # apply to all of them - use 'bots' instead if each one needs its own.
    shared_args = list(bot_args) if bot_args else []
    shared_env = dict(env) if env else {}
    return [{"file": f, "args": list(shared_args), "env": dict(shared_env)} for f in files]


def run(
    bot_file=None,
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
):

    bot_configs = _normalize_bot_configs(bot_file, bot_args, env, bots)

    for cfg in bot_configs:
        if not os.path.isfile(cfg["file"]):
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

    def _bot_cmd(cfg):
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

    def shutdown(signum, frame):
        stopping.set()
        try:
            sig_name = signal.Signals(signum).name
        except ValueError:
            sig_name = str(signum)
        logger.info("Received %s, stopping...", sig_name)

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
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)
    except ValueError:
        # signal handlers can only be registered on the main thread;
        # if run() is called elsewhere, skip graceful signal handling
        # rather than crashing.
        logger.warning(
            "Could not register signal handlers (not running on main thread). "
            "Ctrl+C / SIGTERM will not gracefully stop the bot process(es)."
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
            label = _bot_label(i, cfg["file"], total_bots)
            logger.error("Failed to launch %s: %s", label, exc)
            for started in initial_processes.values():
                started.terminate()
            for started in initial_processes.values():
                started.wait()
            raise
        proc_holder[i] = initial_processes[i]

    def _manage_bot(index, cfg, process):
        label = _bot_label(index, cfg["file"], total_bots)
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
        failed_labels = ", ".join(
            _bot_label(i, bot_configs[i]["file"], total_bots) for i in sorted(failures)
        )
        logger.error(
            "%d of %d bot process(es) failed to stay up: %s",
            len(failures), total_bots, failed_labels,
        )
        worst_exit_code = next((code for code in failures.values() if code), 1)
        sys.exit(_to_process_exit_code(worst_exit_code))
