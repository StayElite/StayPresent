import copy
import os
import re
import threading
from typing import Any

_lock = threading.Lock()

_DEFAULT_PATH = "/"

# Paths StayPresent itself owns - registering a response here would silently
# never be served, since server.py wires up a dedicated Flask route for them
# that always wins over the catch-all route used for user-registered paths.
_RESERVED_PATHS = {"/health"}

# Internal response state, keyed by path so multiple responses can be hosted
# at once (e.g. one bot's status at "/", another's at "/bot2", a dashboard
# at "/dashboard").
#
# Each entry is:
#   {"type": "json" | "text" | "html" | "markdown", "value": ...}
# value is:
#   - "json": a JSON-serializable dict/list
#   - "text": a str
#   - "html" / "markdown": the filesystem path to the file (read fresh on
#     every request)
_routes = {
    _DEFAULT_PATH: {"type": "json", "value": {"message": "I'm Present"}},
}


def _normalize_path(path: str) -> str:
    """
    Validate and canonicalize a route path: ensure it's a non-empty str,
    starts with "/", collapses repeated slashes, and strips any trailing
    slash (except for the root path itself) so "/status" and "/status/"
    are treated as the same route.
    """
    if not isinstance(path, str):
        raise TypeError(f"staypresent.web: 'path' must be a str, got {type(path).__name__}.")
    if not path or not path.strip():
        raise ValueError("staypresent.web: 'path' cannot be empty. Use '/' for the default route.")
    if "?" in path or "#" in path:
        raise ValueError(
            f"staypresent.web: 'path' must not contain query strings or fragments, got '{path}'."
        )

    normalized = path if path.startswith("/") else "/" + path
    normalized = re.sub(r"/+", "/", normalized)
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")

    if normalized in _RESERVED_PATHS:
        raise ValueError(
            f"staypresent.web: path '{normalized}' is reserved for StayPresent's built-in "
            "health check and can't be overridden."
        )

    return normalized


def text(message: str, path: str = "/") -> None:
    """
    Set a plain-text response for the web server to return at `path`.

    Args:
        message: The text to serve.
        path: The route to host this response on. Defaults to "/". Pass a
            different path (e.g. "/status") to host multiple independent
            responses at once - useful when running multiple bots that each
            want their own status endpoint.
    """
    p = _normalize_path(path)
    with _lock:
        _routes[p] = {"type": "text", "value": str(message)}


def json(data: Any, path: str = "/") -> None:
    """
    Set a JSON-serializable response (dict/list) for the web server to
    return at `path`.

    A deep copy of `data` is stored, so mutating the object you passed in
    afterwards (e.g. `my_dict["x"] = 1`) will NOT change the live response.
    Call `staypresent.web.json(...)` again if you want to update it.

    Args:
        data: A JSON-serializable dict or list.
        path: The route to host this response on. Defaults to "/". Pass a
            different path (e.g. "/api") to host multiple independent
            responses at once.
    """
    p = _normalize_path(path)
    with _lock:
        _routes[p] = {"type": "json", "value": copy.deepcopy(data)}


def html(file_path: str, path: str = "/") -> None:
    """
    Serve the content of an HTML file as the web response at `path`.

    The file is read fresh on every incoming request, so you can edit the
    file on disk (e.g. a template) without restarting the bot. Any other
    files (CSS, JS, images) in the same directory are automatically served
    alongside it.

    Example:
        staypresent.web.html("template/index.html")
        staypresent.web.html("template/dashboard.html", path="/dashboard")

    Args:
        file_path: Path to the HTML file to serve.
        path: The route to host this page on. Defaults to "/". When set to
            anything other than "/", requests to the bare path are
            redirected to a trailing-slash version (e.g. "/dashboard" ->
            "/dashboard/") so that relative asset links inside the HTML
            (e.g. `href="style.css"`) resolve against this page's own
            directory instead of its parent.

    Raises:
        FileNotFoundError: if `file_path` does not exist at call time.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"staypresent.web.html(): file '{file_path}' does not exist or is not a file."
        )

    p = _normalize_path(path)
    with _lock:
        _routes[p] = {"type": "html", "value": os.path.abspath(file_path)}


def markdown(file_path: str, path: str = "/") -> None:
    """
    Serve a Markdown (.md) file, rendered to HTML, as the web response at
    `path`.

    The file is read and re-rendered fresh on every incoming request, so
    you can edit it on disk without restarting the bot. Any other files
    (images, etc.) in the same directory are automatically served alongside
    it, the same way `staypresent.web.html()` serves static assets.

    Rendering uses the optional `markdown` package if it's installed
    (`pip install staypresent[md]`). If it isn't installed, the raw
    Markdown source is served instead, safely escaped inside a `<pre>`
    block, and a one-time warning is logged explaining how to get proper
    HTML rendering.

    Example:
        staypresent.web.markdown("CHANGELOG.md")
        staypresent.web.markdown("docs/guide.md", path="/docs")

    Args:
        file_path: Path to the Markdown file to serve.
        path: The route to host this page on. Defaults to "/". Same
            trailing-slash redirect behavior as `html()` applies for
            non-root paths.

    Raises:
        FileNotFoundError: if `file_path` does not exist at call time.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"staypresent.web.markdown(): file '{file_path}' does not exist or is not a file."
        )

    p = _normalize_path(path)
    with _lock:
        _routes[p] = {"type": "markdown", "value": os.path.abspath(file_path)}


def remove(path: str = "/") -> bool:
    """
    Stop hosting a response at `path`.

    Returns:
        True if a response was registered at `path` and has been removed,
        False if nothing was registered there.
    """
    p = _normalize_path(path)
    with _lock:
        return _routes.pop(p, None) is not None


def get(path: str = "/") -> dict:
    """
    Return the currently configured response state for `path` as
    {'type': ..., 'value': ...}, or an empty dict if nothing is registered
    there.
    """
    p = _normalize_path(path)
    with _lock:
        state = _routes.get(p)
    return dict(state) if state is not None else {}


def get_all() -> dict:
    """
    Return every currently registered path -> {'type': ..., 'value': ...}
    mapping. Useful for debugging, testing, or building your own dashboard
    of what StayPresent is currently serving.
    """
    with _lock:
        return {p: dict(state) for p, state in _routes.items()}


def paths() -> list:
    """Return a sorted list of every path currently hosting a response."""
    with _lock:
        return sorted(_routes.keys())
