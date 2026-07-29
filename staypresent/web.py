import copy
import json as _json
import logging
import os
import re
import threading
from typing import Any

logger = logging.getLogger("staypresent")

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

    # Strip surrounding whitespace up front - a stray leading/trailing space
    # (easy to introduce via copy-paste or an f-string, e.g. f" /{name}")
    # would otherwise survive into the "normalized" path (e.g. " /abc" or
    # "/abc "), silently producing a route nothing can ever actually reach,
    # with no error to catch the mistake.
    path = path.strip()

    if "?" in path or "#" in path:
        raise ValueError(
            f"staypresent.web: 'path' must not contain query strings or fragments, got '{path}'."
        )

    normalized = path if path.startswith("/") else "/" + path
    normalized = re.sub(r"/+", "/", normalized)
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized.rstrip("/")

    return normalized


def is_builtin_default_path(path: str) -> bool:
    """
    Return True if `path` is one of StayPresent's own built-in default
    paths (currently just "/health" - see `_BUILTIN_DEFAULT_PATHS` above).

    `server.py`'s catch-all route uses this (rather than hardcoding the
    literal path string itself) to decide whether to fall back to a
    built-in response when nothing has been registered at `path` - so
    adding a new built-in default in the future only means updating
    `_BUILTIN_DEFAULT_PATHS`, not every place that needs to know about it.
    """
    return _normalize_path(path) in _BUILTIN_DEFAULT_PATHS


def _warn_if_overwriting(path: str, previous: dict, new_type: str) -> None:
    """
    Calling text()/json()/html()/markdown() again for a path you've already
    registered (e.g. to update a JSON status payload) is a normal, expected
    pattern - so this never raises or blocks the overwrite. But if two
    different call sites end up registering *different kinds* of responses
    at the same path (most often a sign that two bots, or two unrelated
    parts of the same script, didn't realize they were both claiming "/"
    or the same custom path), only the most recent one is ever served, and
    that's easy to miss silently. This logs a one-line warning whenever the
    response *type* at a path actually changes, so the collision shows up
    in your logs instead of just quietly serving the wrong thing.
    """
    if not previous or previous.get("type") == new_type:
        return
    logger.warning(
        "staypresent.web: path '%s' already had a '%s' response registered - it's now "
        "replaced with a '%s' response. If this wasn't intentional, check whether two "
        "different bots (or two different parts of your code) are both registering a "
        "response at '%s'.",
        path, previous.get("type"), new_type, path,
    )


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
        previous = _routes.get(p)
        _routes[p] = {"type": "text", "value": str(message)}
    _warn_if_overwriting(p, previous, "text")


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

    Raises:
        TypeError: if `data` isn't JSON-serializable.
    """
    try:
        _json.dumps(data)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"staypresent.web.json(): 'data' is not JSON-serializable: {exc}"
        ) from exc

    p = _normalize_path(path)
    with _lock:
        previous = _routes.get(p)
        _routes[p] = {"type": "json", "value": copy.deepcopy(data)}
    _warn_if_overwriting(p, previous, "json")


# Directories we've already warned about, so a bot that calls html()/
# markdown() repeatedly against the same directory (e.g. re-registering a
# route to refresh it) doesn't spam the log every time. Guarded by the same
# `_lock` as `_routes` (not a lock of its own) - simplest way to keep this
# consistent with the rest of this module's shared state, and calls into
# `html()`/`markdown()` are infrequent registration-time operations, not a
# contention hot path.
_warned_directories = set()


def _warn_serves_whole_directory(file_path: str) -> None:
    """
    Log a one-time, hard-to-miss warning that registering `file_path` via
    html()/markdown() serves every file in its directory as a static-asset
    fallback (see server.py's catch_all -> _find_asset_owner) - not just
    files actually referenced from the page. This is "working as designed"
    (it's how relative CSS/JS/image links next to your HTML/Markdown get
    served at all), but the *scope* - whole directory, not an allowlist of
    referenced files - is easy to miss, and a `.env`/`.git/`/bot source
    file sitting in the same directory would be silently downloadable.
    """
    directory = os.path.dirname(os.path.abspath(file_path))
    with _lock:
        if directory in _warned_directories:
            return
        _warned_directories.add(directory)
    logger.warning(
        "staypresent.web: every file inside '%s' is now servable to anyone who requests "
        "it by name (not just files linked from '%s') - this is how relative CSS/JS/image "
        "links next to it get served, but it also means secrets (.env), source files, or "
        "'.git/' in that same directory would be downloadable too. Keep '%s' in a "
        "directory containing only files you're happy to have publicly served.",
        directory, os.path.basename(file_path), directory,
    )


def html(file_path: str, path: str = "/") -> None:
    """
    Serve the content of an HTML file as the web response at `path`.

    The file is read fresh on every incoming request, so you can edit the
    file on disk (e.g. a template) without restarting the bot. Any other
    files (CSS, JS, images) in the same directory are automatically served
    alongside it.

    ⚠️  SECURITY: this means StayPresent will serve *every* file in
    `file_path`'s directory - not just files actually linked/referenced
    from the page - to anyone who requests them by name, for any
    unmatched request path under this route. If a `.env`, your bot's own
    source file, or a `.git/` directory sits next to `file_path`, it is
    downloadable by anyone who guesses (or brute-forces) the filename.
    Put `file_path` in its own directory containing only files you're
    happy to have publicly served, and keep secrets/source elsewhere.

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

    _warn_serves_whole_directory(file_path)

    p = _normalize_path(path)
    with _lock:
        previous = _routes.get(p)
        _routes[p] = {"type": "html", "value": os.path.abspath(file_path)}
    _warn_if_overwriting(p, previous, "html")


_VALID_MARKDOWN_MODES = ("light", "dark", "auto")


def markdown(
    file_path: str,
    path: str = "/",
    mode: str = "auto",
    favicon: str = None,
    title: str = None,
    description: str = None,
) -> None:
    """
    Serve a Markdown (.md) file, rendered to styled HTML, as the web
    response at `path`.

    The file is read and re-rendered fresh on every incoming request, so
    you can edit it on disk without restarting the bot. Rendering uses
    StayPresent's own built-in, dependency-free Markdown renderer (headings,
    bold/italic/strikethrough, links, images, lists, blockquotes, fenced
    code blocks, tables, autolinks, and a GitHub-flavored stylesheet with
    automatic light/dark support) - no extra package required. Any other
    files (images, etc.) in the same directory are automatically served
    alongside it, the same way `staypresent.web.html()` serves static
    assets.

    ⚠️  SECURITY: same as `staypresent.web.html()` - every file in
    `file_path`'s directory becomes servable to anyone who requests it by
    name, not just files actually referenced from the rendered page. Keep
    `file_path` in a directory containing only files you're happy to have
    publicly served.

    Example:
        staypresent.web.markdown("CHANGELOG.md")
        staypresent.web.markdown(
            "docs/guide.md",
            path="/docs",
            mode="dark",
            favicon="favicon.png",
            title="Project Docs",
            description="Everything you need to get started.",
        )

    Args:
        file_path: Path to the Markdown file to serve.
        path: The route to host this page on. Defaults to "/". Same
            trailing-slash redirect behavior as `html()` applies for
            non-root paths.
        mode: Color scheme for the rendered page - one of "light", "dark",
            or "auto" (default). "auto" follows the visitor's OS/browser
            preference via `prefers-color-scheme`; "light"/"dark" force
            that scheme regardless of the visitor's own setting.
        favicon: Optional favicon to add to the page. A direct URL
            (starting with "http://", "https://", or "//") is used as-is;
            anything else (e.g. "favicon.png") is treated as a path next to
            `file_path` and resolved the same way neighboring assets
            already are - so it must actually exist alongside your
            Markdown file to be served correctly.
        title: Optional page `<title>` (and Open Graph title). Defaults to
            the Markdown file's own filename when omitted.
        description: Optional page description, added as both a standard
            `<meta name="description">` tag and an Open Graph description
            tag - useful for link-preview cards on social media/chat apps.

    Raises:
        FileNotFoundError: if `file_path` does not exist at call time.
        ValueError: if `mode` isn't "light", "dark", or "auto".
        TypeError: if `favicon`, `title`, or `description` is set to
            something other than a str.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"staypresent.web.markdown(): file '{file_path}' does not exist or is not a file."
        )

    if mode is None:
        mode = "auto"
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

    if favicon and not favicon.startswith(("http://", "https://", "//")):
        # Not a direct URL - resolved the same way neighboring assets are:
        # relative to file_path's own directory. Check it exists up front,
        # the same way file_path itself is checked above, rather than
        # letting a typo'd favicon silently 404 only when a browser
        # actually requests it.
        favicon_path = os.path.join(os.path.dirname(os.path.abspath(file_path)), favicon)
        if not os.path.isfile(favicon_path):
            raise FileNotFoundError(
                f"staypresent.web.markdown(): favicon '{favicon}' does not exist next to "
                f"'{file_path}' (looked for '{favicon_path}')."
            )

    _warn_serves_whole_directory(file_path)

    p = _normalize_path(path)
    with _lock:
        previous = _routes.get(p)
        _routes[p] = {
            "type": "markdown",
            "value": os.path.abspath(file_path),
            "mode": mode,
            "favicon": favicon,
            "title": title,
            "description": description,
        }
    _warn_if_overwriting(p, previous, "markdown")


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
    Return the currently configured response state for `path` as a dict
    (e.g. {'type': 'json', 'value': {...}}, or with 'mode'/'favicon'/
    'title'/'description' keys too for a "markdown" entry), or an empty
    dict if nothing is registered there.
    """
    p = _normalize_path(path)
    with _lock:
        state = _routes.get(p)
    return dict(state) if state is not None else {}


def get_all() -> dict:
    """
    Return every currently registered path -> state mapping. Useful for
    debugging, testing, or building your own dashboard of what
    StayPresent is currently serving.
    """
    with _lock:
        return {p: dict(state) for p, state in _routes.items()}


def paths() -> list:
    """Return a sorted list of every path currently hosting a response."""
    with _lock:
        return sorted(_routes.keys())
