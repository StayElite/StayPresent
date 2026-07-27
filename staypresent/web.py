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
    
    p = _normalize_path(path)
    with _lock:
        _routes[p] = {"type": "text", "value": str(message)}


def json(data: Any, path: str = "/") -> None:
    
    p = _normalize_path(path)
    with _lock:
        _routes[p] = {"type": "json", "value": copy.deepcopy(data)}


def html(file_path: str, path: str = "/") -> None:
    
    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"staypresent.web.html(): file '{file_path}' does not exist or is not a file."
        )

    p = _normalize_path(path)
    with _lock:
        _routes[p] = {"type": "html", "value": os.path.abspath(file_path)}


def markdown(file_path: str, path: str = "/") -> None:
    
    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"staypresent.web.markdown(): file '{file_path}' does not exist or is not a file."
        )

    p = _normalize_path(path)
    with _lock:
        _routes[p] = {"type": "markdown", "value": os.path.abspath(file_path)}


def remove(path: str = "/") -> bool:
    
    p = _normalize_path(path)
    with _lock:
        return _routes.pop(p, None) is not None


def get(path: str = "/") -> dict:
    
    p = _normalize_path(path)
    with _lock:
        state = _routes.get(p)
    return dict(state) if state is not None else {}


def get_all() -> dict:
    
    with _lock:
        return {p: dict(state) for p, state in _routes.items()}


def paths() -> list:
    
    with _lock:
        return sorted(_routes.keys())
