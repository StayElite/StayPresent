import logging
import threading
import time
import urllib.error
import urllib.request

logger = logging.getLogger("staypresent")

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_ANY_HOSTS = {"0.0.0.0", "::", ""}


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

    @property
    def is_running(self) -> bool:
        return self._thread.is_alive() and not self._stop_event.is_set()


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

    return CronHandle(thread, stop_event, url)