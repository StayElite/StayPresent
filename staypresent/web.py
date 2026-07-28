import copy
import os
import re
import threading
from typing import Any

_lock = threading.Lock()

_DEFAULT_PATH = "/"

# Paths Stay Present ships a built-in default for. Registering a response
# at one of these paths overrides that default (see server.py's catch_all,
# which only falls back to the built-in behavior when nothing is
# registered here) - it's not blocked the way truly internal paths would
# be, since there currently are none.
_BUILTIN_DEFAULT_PATHS = {"/health"}

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


_VALID_MARKDOWN_MODES = ("light", "dark", "auto")


def markdown(
    file_path: str,
    path: str = "/",
    mode: str = "auto",
    favicon: str = None,
    title: str = None,
    description: str = None,
) -> None:
    

    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"staypresent.web.markdown(): file '{file_path}' does not exist or is not a file."
        )

    if not isinstance(mode, str) or mode.strip().lower() not in _VALID_MARKDOWN_MODES:
        raise ValueError(
            "staypresent.web.markdown(): 'mode' must be one of 'light', 'dark', or "
            f"'auto', got {mode!r}."
        )
    mode = mode.strip().lower()

    for name, value in (("favicon", favicon), ("title", title), ("description", description)):
        if value is not None and not isinstance(value, str):
            raise TypeError(
                f"staypresent.web.markdown(): '{name}' must be a str or None, got {type(value).__name__}."
            )

    p = _normalize_path(path)
    with _lock:
        _routes[p] = {
            "type": "markdown",
            "value": os.path.abspath(file_path),
            "mode": mode,
            "favicon": favicon,
            "title": title,
            "description": description,
        }


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