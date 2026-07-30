"""
StayPresent - Ping / Keep-Warm

staypresent.ping() for one-off HTTP health checks, and staypresent.cron()
for a recurring background pinger that keeps a free-tier host from
spinning your service down due to inactivity.

Part of the StayPresent project.
Docs: https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.md
"""

# Created and maintained by Ashish Sharma (Stay Elite).
# Copyright (c) 2026 Ashish Sharma (Stay Elite)
# Licensed under the MIT License. See the LICENSE file for details.

import logging
import threading
import time
import urllib.error
import urllib.request

logger = logging.getLogger("staypresent")

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
# "0.0.0.0"/"::" are bind addresses, not something you can send an outgoing
# request to - treated as "this machine" below. (An empty-string host is
# NOT included here: _build_url() already raises ValueError for an
# empty/whitespace-only host before this set is ever consulted, so an ""
# entry here would be unreachable dead code.)
_ANY_HOSTS = {"0.0.0.0", "::"}

# Every CronHandle ever returned by cron(), tracked with a *strong*
# reference so this registry keeps working for the common "fire-and-forget"
# pattern - e.g. `pinger.cron(...)` called without keeping the returned
# handle around, which is a completely normal way to use a keep-warm
# pinger nobody intends to ever `.stop()`. (An earlier version of this used
# a weakref.WeakSet so the registry wouldn't keep the handle's *thread*
# alive artificially - but a plain CronHandle object holds no thread alive
# by existing; its background thread is already a daemon thread that dies
# with the process regardless of whether anything still references the
# handle. Using a WeakSet there meant the handle got garbage-collected
# right after cron() returned whenever the caller discarded the return
# value, making the job vanish from introspection even though its thread
# kept running.) Dead entries (thread no longer alive) are pruned lazily
# whenever the registry is read or a handle is stopped, so this doesn't
# grow unbounded over a long-running process either.
_cron_registry = set()
_cron_registry_lock = threading.Lock()


def _prune_cron_registry():
    with _cron_registry_lock:
        dead = [h for h in _cron_registry if not h._thread.is_alive()]
        for h in dead:
            _cron_registry.discard(h)


def _build_url(host: str, port: int = None, path: str = "/", https: bool = None) -> str:
    if not isinstance(host, str):
        raise TypeError(f"staypresent.ping()/cron(): 'host' must be a str, got {type(host).__name__}.")
    if port is not None and not isinstance(port, int):
        raise TypeError(f"staypresent.ping()/cron(): 'port' must be an int, got {type(port).__name__}.")
    if not isinstance(path, str):
        raise TypeError(f"staypresent.ping()/cron(): 'path' must be a str, got {type(path).__name__}.")
    if not host or not host.strip():
        raise ValueError("staypresent.ping()/cron(): 'host' is required.")
    host = host.strip()

    # Already a full URL (e.g. "https://google.com" or "http://1.2.3.4:9000/x")
    if "://" in host:
        if port is not None or (path and path != "/") or https is not None:
            logger.warning(
                "staypresent.ping()/cron(): 'host' is already a full URL (%s) - "
                "the 'port'/'path'/'https' arguments are ignored.",
                host,
            )
        return host

    # "0.0.0.0" / "::" is a *bind* address, not something you can send an
    # outgoing request to on every platform - treat it as "this machine".
    target_host = "127.0.0.1" if host in _ANY_HOSTS else host

    if port is not None and not (1 <= port <= 65535):
        raise ValueError(f"staypresent.ping()/cron(): port must be between 1 and 65535, got {port}.")

    if https is None:
        # Bare local addresses default to http (that's what staypresent.run()
        # itself serves); anything else is assumed to be a public https site.
        https = target_host not in _LOCAL_HOSTS

    scheme = "https" if https else "http"
    netloc = f"{target_host}:{port}" if port else target_host

    if not path.startswith("/"):
        path = "/" + path

    return f"{scheme}://{netloc}{path}"


def ping(host: str, port: int = None, path: str = "/", timeout: float = 10.0, https: bool = None) -> dict:
    """
    Send a single HTTP GET request to `host` (a bare host/IP, "host:port",
    or a full URL) and report the result.

    Args:
        host: Hostname/IP, or a full URL (in which case `port`/`path`/
            `https` are ignored). "0.0.0.0"/"::" are treated as "this
            machine" (127.0.0.1), since they're bind addresses, not
            something you can send an outgoing request to.
        port: Port to connect to. Ignored if `host` is a full URL.
        path: URL path to request. Ignored if `host` is a full URL.
        timeout: Seconds to wait for a response before giving up.
        https: Force https (True) or http (False). If omitted, defaults to
            https for anything that isn't a local address, and http for
            "127.0.0.1"/"localhost"/"::1" (matching what `staypresent.run()`
            itself serves).

    Returns:
        A dict: {"url", "ok", "status_code", "elapsed", "error"}. `ok` is
        True for any 2xx/3xx response. `error` holds a short description on
        failure (HTTP error status, timeout, DNS failure, connection
        refused, etc.), else None.
    """
    if timeout <= 0:
        raise ValueError(f"staypresent.ping(): timeout must be > 0, got {timeout}.")

    url = _build_url(host, port, path, https)
    result = {"url": url, "ok": False, "status_code": None, "elapsed": None, "error": None}

    started = time.monotonic()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "staypresent-ping"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result["status_code"] = response.status
            result["ok"] = 200 <= response.status < 400
    except urllib.error.HTTPError as exc:
        # Server responded, but with an error status (4xx/5xx) - still
        # "reachable", just not a healthy response.
        result["status_code"] = exc.code
        result["error"] = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - DNS failures, timeouts, connection refused, etc.
        result["error"] = str(exc)
    finally:
        result["elapsed"] = round(time.monotonic() - started, 3)

    if result["ok"]:
        logger.debug("Ping to %s succeeded (status %s, %.3fs)", url, result["status_code"], result["elapsed"])
    else:
        logger.warning("Ping to %s failed: %s", url, result["error"])

    return result


class CronHandle:

    def __init__(self, thread: threading.Thread, stop_event: threading.Event, url: str):
        self._thread = thread
        self._stop_event = stop_event
        self._url = url

    def stop(self, wait: bool = False, timeout: float = None) -> None:
        """Stop the background pinger. Safe to call more than once."""
        if not self._stop_event.is_set():
            logger.info("Stopping cron pinger for %s", self._url)
        self._stop_event.set()
        if wait:
            self._thread.join(timeout=timeout)
        with _cron_registry_lock:
            _cron_registry.discard(self)

    @property
    def is_running(self) -> bool:
        return self._thread.is_alive() and not self._stop_event.is_set()

    @property
    def url(self) -> str:
        """The URL this cron job pings."""
        return self._url


def cron(
    host: str,
    port: int = None,
    path: str = "/",
    interval: float = 300.0,
    repeat: bool = True,
    timeout: float = 10.0,
    https: bool = None,
    on_success=None,
    on_failure=None,
) -> CronHandle:
    """
    Start a background thread that repeatedly pings a URL - useful for
    keeping a free-tier host "warm" (preventing it from spinning your
    service down due to inactivity).

    Args:
        host, port, path, https: Same as `ping()` - describe the URL to hit.
        interval: Seconds to wait between pings.
        repeat: If True (default), keep pinging forever (until `.stop()` is
            called). If False, ping exactly once and stop.
        timeout: Per-request timeout in seconds, same as `ping()`.
        on_success: Optional callback `fn(result)` called after each
            successful ping (`result` is the same dict `ping()` returns).
            An exception raised by the callback is logged and swallowed -
            it will not stop the cron loop.
        on_failure: Optional callback `fn(result)` called after each failed
            ping. Same exception-safety as `on_success`.

    Returns:
        A `CronHandle` you can use to stop the background pinger later via
        `handle.stop()`, or check `handle.is_running`.
    """
    if interval <= 0:
        raise ValueError(f"staypresent.cron(): interval must be > 0, got {interval}.")
    if timeout <= 0:
        raise ValueError(f"staypresent.cron(): timeout must be > 0, got {timeout}.")

    # Validate the URL/host up front so bad input fails immediately, not
    # silently inside the background thread on the first tick.
    url = _build_url(host, port, path, https)

    stop_event = threading.Event()

    def _loop():
        while True:
            result = ping(host, port=port, path=path, timeout=timeout, https=https)

            callback = on_success if result["ok"] else on_failure
            if callback is not None:
                try:
                    callback(result)
                except Exception:  # noqa: BLE001 - a bad callback must not kill the cron thread
                    logger.exception("staypresent.cron(): callback raised an exception.")

            if not repeat or stop_event.wait(timeout=interval):
                break

    if repeat:
        interval_str = f"{interval:g}"
        logger.info("Started cron: pinging %s every %ss", url, interval_str)
    else:
        logger.info("Started cron: pinging %s once", url)

    thread = threading.Thread(target=_loop, daemon=True, name=f"staypresent-cron-{host}")
    thread.start()

    handle = CronHandle(thread, stop_event, url)
    with _cron_registry_lock:
        _cron_registry.add(handle)
    return handle


def active_cron_handles() -> list:
    """
    Return every currently-registered `CronHandle` (from any past call to
    `cron()`) whose background thread is still running - i.e. `.is_running`
    is True. Handles that have been stopped, or whose thread has otherwise
    exited, are left out.

    Useful for introspecting cron jobs that are still active - for example,
    `staypresent.run()`'s own shutdown sequence uses this to log any cron
    pinger(s) still ticking when the process is asked to stop.
    """
    _prune_cron_registry()
    with _cron_registry_lock:
        handles = list(_cron_registry)
    return [h for h in handles if h.is_running]