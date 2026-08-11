"""
StayPresent - Web Response Registry

Lets a bot register what the web server should return, and at which
path: plain text, JSON, static HTML, or rendered Markdown. Supports
hosting multiple independent responses at once (e.g. one per bot).

Part of the StayPresent project.
Docs: https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.md
"""

# Created and maintained by Ashish Sharma (Stay Elite).
# Copyright (c) 2026 Ashish Sharma (Stay Elite)
# Licensed under the MIT License. See the LICENSE file for details.

import copy
import fnmatch
import json as _json
import logging
import os
import re
import secrets
import threading
from typing import Any

from . import status_registry

logger = logging.getLogger("staypresent")

_lock = threading.Lock()


# The path a status page is served on when `staypresent.web.status()`
# is called without an explicit `path` - and, more importantly, the path
# that implicitly serves a status page even when `web.status()` is never
# called at all (see `_default_status_state()`/`_BUILTIN_DEFAULT_RESPONSES`
# below). Kept as a named constant since it's referenced from a few
# places that all need to agree on it.
_DEFAULT_STATUS_PATH = "/status"

# Paths Stay Present ships a built-in default for. Registering a response
# at one of these paths overrides that default (see server.py's catch_all,
# which only falls back to the built-in behavior when nothing is
# registered here) - it's not blocked the way truly internal paths would
# be, since there currently are none.
_BUILTIN_DEFAULT_PATHS = {"/", "/health", _DEFAULT_STATUS_PATH}

# The state used for the implicitly-active default status page at
# _DEFAULT_STATUS_PATH ("/status") whenever nothing else is registered
# there (see server.py's catch_all) - the same fallback role "/health"
# (and "/", see _BUILTIN_DEFAULT_RESPONSES below) plays. This is a
# template, never handed out directly: _default_status_state() always
# returns a fresh deep copy, so no caller (including get()/get_all()
# themselves) can ever end up holding a reference to shared mutable state -
# a future accidental mutation of a returned dict's "footer_links"
# can only ever affect that one copy, never every subsequent request.
_DEFAULT_STATUS_STATE_TEMPLATE = {
    "type": "status",
    "title": "Service Status",
    "copyright": None,
    "footer_links": [],
    "api_key": None,
    "trust_proxy_headers": False,
    "mode": "auto",
    "favicon": None,
    "description": None,
    "poll_seconds": 15,
}

# Lazily generated the first time the implicit default status page (see
# _default_status_state() below) is actually asked for, so a project that
# never calls staypresent.web.status() itself still gets a working admin
# login instead of none at all - the same reasoning status() itself now
# applies to an explicit call with no api_key given (see status() below).
# Generated once and cached (not regenerated per request/deep-copy) so
# the key an admin was shown in the log stays valid for the life of this
# process.
_auto_default_api_key = None
_auto_default_api_key_lock = threading.Lock()


def _get_or_create_default_api_key() -> str:
    global _auto_default_api_key
    with _auto_default_api_key_lock:
        if _auto_default_api_key is None:
            _auto_default_api_key = secrets.token_urlsafe(32)
            logger.info(
                "staypresent: no api_key configured for the default status page at "
                "'%s' - generated a random session key so its admin view still works: "
                "%s (call staypresent.web.status(api_key=...) yourself for a fixed key "
                "that survives a restart, or api_key=\"\" to disable the admin view).",
                _DEFAULT_STATUS_PATH, _auto_default_api_key,
            )
        return _auto_default_api_key


def _default_status_state() -> dict:
    """A fresh, independent copy of the implicit default status-page state."""
    state = copy.deepcopy(_DEFAULT_STATUS_STATE_TEMPLATE)
    state["api_key"] = _get_or_create_default_api_key()
    return state


# Fixed response state for StayPresent's other built-in default paths -
# "/" (a plain "I'm Present" heartbeat message) and "/health" - same
# "implicitly active until overridden" role as _default_status_state()
# above for _DEFAULT_STATUS_PATH, kept separate since these are plain,
# already-immutable values (bool/str-only dicts) with no mutable nested
# containers, so no per-call copy factory is needed for them.
_BUILTIN_DEFAULT_RESPONSES = {
    "/": {"type": "json", "value": {"message": "I'm Present"}},
    "/health": {"type": "json", "value": {"status": "ok"}},
}


# Internal response state, keyed by path so multiple responses can be hosted
# at once (e.g. one bot's status at "/", another's at "/bot2", a dashboard
# at "/dashboard").
#
# Each entry is:
#   {"type": "json" | "text" | "html" | "markdown" | "status", "value": ...}
# value is:
#   - "json": a JSON-serializable dict/list
#   - "text": a str
#   - "html" / "markdown": the filesystem path to the file (read fresh on
#     every request)
#   - "status": unused - a "status" entry's own fields (title, api_key,
#     etc, see web.status()) carry everything server.py needs instead.
#
# Nothing is pre-populated here for "/" (or anywhere else): server.py's
# catch_all falls back to a default "I'm Present" message at "/", a
# default status page at "/status", and a default {"status": "ok"} at
# "/health", whenever nothing is registered at those paths - virtual
# defaults, not real entries here, so registering your own response at
# any of them (via status()/json()/text()/html()/markdown()) is never
# reported as "overwriting" something.
_routes = {}


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
    paths - "/" (a plain "I'm Present" message), "/health", or "/status"
    (the default status page) - see `_BUILTIN_DEFAULT_PATHS` above.

    `server.py`'s catch-all route uses this (rather than hardcoding the
    literal path strings themselves) to decide whether to fall back to a
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


_SERVICES_NAME_DESCRIPTION_DOC = """\
        services_name: Optional display name for this process's row on
            the status page - shorthand for `staypresent.web.services()`
            (removed) covering the common case of tagging one bot from
            right where you set up its response, instead of a separate
            call elsewhere. Applies to whichever single bot
            `staypresent.run()` ends up configuring in this process, or
            to the web server's own row when `run()` is given no bot at
            all - resolved once `run()` actually runs (this can be, and
            normally is, called before it). Raises `TypeError` from
            `run()` itself if this process ends up with more than one
            bot, since a single string can't unambiguously name any one
            of them - tag each bot individually in that case instead, via
            `bots=[{"file": "a.py", "services_name": "Bot A"}, ...]`.
            Whichever of this, `staypresent.run(services_name=...)`, or
            another `staypresent.web.*` call is made last wins outright.
        services_description: Optional description shown under that same
            row's name on the status page. Same resolution and
            last-call-wins behavior as `services_name` above.
"""


def _apply_services_override(services_name, services_description, caller: str) -> None:
    if services_name is not None or services_description is not None:
        status_registry.set_pending_single_target_override(
            services_name, services_description, caller=caller
        )


def _validate_status_param(status, caller: str) -> bool:
    if not isinstance(status, bool):
        raise TypeError(f"{caller}: 'status' must be a bool, got {type(status).__name__}.")
    return status


_STATUS_PARAM_DOC = """\
        status: Whether this route gets its own row on the status page
            (see `staypresent.web.status()`) at all. Defaults to False -
            a route registered here is NOT shown on the status page
            unless you opt it in with `status=True`. This never affects
            whether the route itself is served - only whether it shows
            up as a row on the status page. (This is the opposite
            default `staypresent.run()`'s own `status` uses for a bot/
            worker process, which defaults to True - shown unless you
            explicitly turn it off.)
"""


def text(
    message: str,
    path: str = "/",
    services_name: str = None,
    services_description: str = None,
    status: bool = False,
) -> None:
    """
    Set a plain-text response for the web server to return at `path`.

    Args:
        message: The text to serve.
        path: The route to host this response on. Defaults to "/". Pass a
            different path (e.g. "/status") to host multiple independent
            responses at once - useful when running multiple bots that each
            want their own status endpoint.
""" + _SERVICES_NAME_DESCRIPTION_DOC + _STATUS_PARAM_DOC + """
    Raises:
        TypeError: if `services_name`/`services_description` is set to
            something other than a str, or if `status` isn't a bool.
    """
    status = _validate_status_param(status, "staypresent.web.text()")
    _apply_services_override(services_name, services_description, "staypresent.web.text()")
    p = _normalize_path(path)
    with _lock:
        previous = _routes.get(p)
        _routes[p] = {"type": "text", "value": str(message), "status": status}
    _warn_if_overwriting(p, previous, "text")


def json(
    data: Any,
    path: str = "/",
    services_name: str = None,
    services_description: str = None,
    status: bool = False,
) -> None:
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
""" + _SERVICES_NAME_DESCRIPTION_DOC + _STATUS_PARAM_DOC + """
    Raises:
        TypeError: if `data` isn't JSON-serializable, if
            `services_name`/`services_description` is set to something
            other than a str, or if `status` isn't a bool.
    """
    try:
        _json.dumps(data)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"staypresent.web.json(): 'data' is not JSON-serializable: {exc}"
        ) from exc
    status = _validate_status_param(status, "staypresent.web.json()")
    _apply_services_override(services_name, services_description, "staypresent.web.json()")

    p = _normalize_path(path)
    with _lock:
        previous = _routes.get(p)
        _routes[p] = {"type": "json", "value": copy.deepcopy(data), "status": status}
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


def _normalize_exclude(exclude, func_name: str) -> tuple:
    """
    Validate and normalize the `exclude` parameter shared by html()/
    markdown(): a list of filename/extension patterns that must never be
    served out of file_path's own directory as a neighboring static asset
    (see server.py's _find_asset_owner) - the deny-list counterpart to the
    "whole directory is exposed" warning above.

    Each entry is matched, case-insensitively, against every path segment
    of a candidate file - not just its final filename - via fnmatch-style
    globbing (`*`/`?`/`[seq]`), so a pattern excludes a match at any depth
    under the directory, not just directly inside it (e.g. excluding
    ".git" also blocks "sub/.git/config", not just a file literally named
    ".git" in the top-level directory). A pattern containing "/" (e.g.
    "private/secret.txt") is instead matched against the whole relative
    path (at any depth, e.g. also matching "a/private/secret.txt"), since
    no single segment ever contains a "/" for a segment-only match to
    fire against. For convenience, a plain extension like ".env" is
    treated the same as the explicit glob "*.env" (anything ending in
    ".env"); an entry that already contains a wildcard is used exactly as
    given; anything else (e.g. "secrets.json") matches that exact
    filename, at any depth.

    If two or more html()/markdown() routes serve out of the *same*
    directory with different `exclude` lists, every request resolving to
    that directory is checked against the union of all of them - a
    security-relevant exclusion set by any one route applies no matter
    which route's registration "wins" a given request, rather than
    depending on registration order.
    """
    if exclude is None:
        return ()
    if not isinstance(exclude, (list, tuple)):
        raise TypeError(
            f"staypresent.web.{func_name}(): 'exclude' must be a list of strings, got "
            f"{type(exclude).__name__}."
        )
    patterns = []
    for i, item in enumerate(exclude):
        if not isinstance(item, str) or not item:
            raise TypeError(f"staypresent.web.{func_name}(): exclude[{i}] must be a non-empty str.")
        pattern = item
        if pattern.startswith(".") and not any(c in pattern for c in "*?["):
            pattern = "*" + pattern
        patterns.append(pattern)
    return tuple(patterns)


def _path_excluded(relative_path: str, patterns) -> bool:
    """
    True if any segment of `relative_path` (a path relative to a served
    directory, e.g. "sub/.env" or "secrets.json") matches any of
    `patterns` (already normalized by `_normalize_exclude()` above).

    A pattern containing "/" (e.g. "private/secret.txt") is matched
    against the whole path instead of a single segment - no individual
    segment ever contains a "/", so segment-by-segment matching alone
    would never fire for a pattern like that, silently excluding nothing
    at all despite looking like a valid, more-specific pattern. Matched
    against every *suffix* of the path (dropping leading segments one at
    a time), so "private/secret.txt" excludes that file however deep it
    sits (e.g. "a/private/secret.txt" too), not only when "private" is
    directly inside the served directory.
    """
    if not patterns:
        return False
    normalized = relative_path.replace("\\", "/").strip("/")
    if not normalized:
        return False
    parts = [p for p in normalized.split("/") if p]
    if not parts:
        return False
    suffixes = ["/".join(parts[i:]) for i in range(len(parts))]

    for pattern in patterns:
        pattern_lower = pattern.lower()
        if "/" in pattern:
            if any(fnmatch.fnmatch(suffix.lower(), pattern_lower) for suffix in suffixes):
                return True
            continue
        if any(fnmatch.fnmatch(part.lower(), pattern_lower) for part in parts):
            return True
    return False


def html(
    file_path: str,
    path: str = "/",
    exclude: list = None,
    services_name: str = None,
    services_description: str = None,
    status: bool = False,
) -> None:
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
    happy to have publicly served, and keep secrets/source elsewhere - or
    use `exclude` below to block specific files/extensions outright.

    Example:
        staypresent.web.html("template/index.html")
        staypresent.web.html("template/dashboard.html", path="/dashboard")
        staypresent.web.html("template/index.html", exclude=[".env", ".git", "*.py", "secrets.json"])

    Args:
        file_path: Path to the HTML file to serve.
        path: The route to host this page on. Defaults to "/". When set to
            anything other than "/", requests to the bare path are
            redirected to a trailing-slash version (e.g. "/dashboard" ->
            "/dashboard/") so that relative asset links inside the HTML
            (e.g. `href="style.css"`) resolve against this page's own
            directory instead of its parent.
        exclude: Optional list of filename/extension patterns to always
            deny from `file_path`'s directory, regardless of any other
            route also serving that directory - see
            `staypresent.web._normalize_exclude`'s docstring, or
            [Section 3.3](DOCUMENTATION.md#33-html--static-assets), for
            exactly how patterns are matched. A request for an excluded
            file gets a plain 404, the same as if it didn't exist.
""" + _SERVICES_NAME_DESCRIPTION_DOC + _STATUS_PARAM_DOC + """
    Raises:
        FileNotFoundError: if `file_path` does not exist at call time.
        TypeError: if `exclude` (or an entry within it) has the wrong
            shape, if `services_name`/`services_description` is set to
            something other than a str, or if `status` isn't a bool.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"staypresent.web.html(): file '{file_path}' does not exist or is not a file."
        )

    exclude_patterns = _normalize_exclude(exclude, "html")
    status = _validate_status_param(status, "staypresent.web.html()")
    _apply_services_override(services_name, services_description, "staypresent.web.html()")

    _warn_serves_whole_directory(file_path)

    p = _normalize_path(path)
    with _lock:
        previous = _routes.get(p)
        _routes[p] = {
            "type": "html",
            "value": os.path.abspath(file_path),
            "exclude": exclude_patterns,
            "status": status,
        }
    _warn_if_overwriting(p, previous, "html")


_VALID_MARKDOWN_MODES = ("light", "dark", "auto")


def markdown(
    file_path: str,
    path: str = "/",
    mode: str = "auto",
    favicon: str = None,
    title: str = None,
    description: str = None,
    exclude: list = None,
    services_name: str = None,
    services_description: str = None,
    status: bool = False,
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
    publicly served - or use `exclude` below to block specific files/
    extensions outright.

    Example:
        staypresent.web.markdown("CHANGELOG.md")
        staypresent.web.markdown(
            "docs/guide.md",
            path="/docs",
            mode="dark",
            favicon="favicon.png",
            title="Project Docs",
            description="Everything you need to get started.",
            exclude=[".env", ".git", "*.py"],
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
        exclude: Optional list of filename/extension patterns to always
            deny from `file_path`'s directory, regardless of any other
            route also serving that directory - see
            `staypresent.web._normalize_exclude`'s docstring, or
            [Section 3.3](DOCUMENTATION.md#33-html--static-assets), for
            exactly how patterns are matched. A request for an excluded
            file gets a plain 404, the same as if it didn't exist. If
            `favicon` is a local file that a pattern here would itself
            exclude, this raises `ValueError` up front rather than
            registering a favicon that would silently 404 for every
            visitor.
""" + _SERVICES_NAME_DESCRIPTION_DOC.replace(
        "services_description: Optional description shown under",
        "services_description: Not the same thing as this function's own "
        "`description` above (that one's the rendered page's own "
        "<meta name=\"description\">, this one's the status page's) - "
        "optional description shown under",
    ) + _STATUS_PARAM_DOC + """
    Raises:
        FileNotFoundError: if `file_path` does not exist at call time.
        ValueError: if `mode` isn't "light", "dark", or "auto", or if
            `favicon` is excluded by `exclude` (see above).
        TypeError: if `favicon`, `title`, `description`, `services_name`,
            or `services_description` is set to something other than a
            str, if `exclude` (or an entry within it) has the wrong
            shape, or if `status` isn't a bool.
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

    exclude_patterns = _normalize_exclude(exclude, "markdown")
    status = _validate_status_param(status, "staypresent.web.markdown()")
    _apply_services_override(services_name, services_description, "staypresent.web.markdown()")

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
        if _path_excluded(favicon, exclude_patterns):
            raise ValueError(
                f"staypresent.web.markdown(): favicon '{favicon}' is blocked by 'exclude' "
                f"({exclude!r}) - it would never actually be servable. Either pick a favicon "
                "filename that doesn't match an excluded pattern, or adjust 'exclude'."
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
            "exclude": exclude_patterns,
            "status": status,
        }
    _warn_if_overwriting(p, previous, "markdown")


def _validate_footer_links(footer_links) -> list:
    if footer_links is None:
        return []
    if not isinstance(footer_links, (list, tuple)):
        raise TypeError(
            f"staypresent.web.status(): 'footer_links' must be a list of dicts, got "
            f"{type(footer_links).__name__}."
        )
    validated = []
    for i, link in enumerate(footer_links):
        if not isinstance(link, dict):
            raise TypeError(f"staypresent.web.status(): footer_links[{i}] must be a dict, got {type(link).__name__}.")
        label, url = link.get("label"), link.get("url")
        if not isinstance(label, str) or not label:
            raise TypeError(f"staypresent.web.status(): footer_links[{i}]['label'] must be a non-empty str.")
        if not isinstance(url, str) or not url:
            raise TypeError(f"staypresent.web.status(): footer_links[{i}]['url'] must be a non-empty str.")
        validated.append({"label": label, "url": url})
    return validated


def status(
    title: str = None,
    path: str = _DEFAULT_STATUS_PATH,
    copyright: str = None,
    footer_links: list = None,
    api_key: str = None,
    trust_proxy_headers: bool = False,
    mode: str = "auto",
    favicon: str = None,
    description: str = None,
    poll_seconds: float = 15,
    status: bool = False,
) -> None:
    """
    Serve a built-in, auto-updating status page at `path` - service list
    (one row per bot given to `staypresent.run()`, by default named after
    its own file/module), an uptime chart, and a rolling incident history,
    all derived automatically from what StayPresent already observes about
    each bot (launches, crashes, restarts, permanent failures). Nothing on
    the page is fabricated: a metric StayPresent doesn't actually know
    (e.g. response time for a background bot that isn't itself an HTTP
    endpoint) is simply left off rather than shown as a fake number.

    The page polls its own live data endpoint every `poll_seconds`
    seconds (15 by default), so it stays current without needing a
    manual refresh.

    Example:
        staypresent.web.status(title="Groundflare Bots Status")
        staypresent.web.status(
            title="Groundflare Bots Status",
            copyright="Groundflare Inc.",
            footer_links=[{"label": "Contact Support", "url": "https://Ground.flare/support"}],
            api_key="a-long-random-secret",
            mode="dark",
            favicon="https://groundflare.example/favicon.png",
            description="Live status for Groundflare's bots.",
        )

        To rename this process's service row, pass services_name/
        services_description to staypresent.run() (single-bot/no-bot) or
        to a specific bots[i] entry (multi-bot), or to whichever
        staypresent.web.html()/json()/text()/markdown() call sets up this
        process's own response - these apply process-wide, to every
        status page:
        staypresent.web.markdown(
            "CHANGELOG.md",
            services_name="Telegram Bot",
            services_description="Customer chat support",
        )

    Args:
        title: Page title/heading. Defaults to "Service Status".
        path: The route to host this page on. Defaults to "/status" - a
            status page is served there automatically even if this
            function is never called at all; call this only to customize
            it or to move it to a different path. Same trailing-slash
            redirect behavior as `html()`/`markdown()` applies for
            non-root paths, since this page's CSS/JS/data endpoint are
            served relative to it.
        copyright: Optional copyright line shown in the footer (e.g.
            "Groundflare Inc." renders "© <year> Groundflare Inc."). Omitted entirely
            when not given - this is separate from, and doesn't replace,
            the "Powered by StayPresent" credit, which always appears.
        footer_links: Optional list of `{"label": ..., "url": ...}` dicts
            shown as a row of links in the footer (e.g. a support/contact
            page). Omitted entirely when not given.
        api_key: Optional secret enabling an admin login. The page itself,
            and its CSS/JS/data endpoint, are always visible to everyone
            regardless of this setting - only the technical detail behind
            an incident (the actual exit code) is gated behind it, via a
            small "Admin" link in the page's footer that accepts the key
            through an `X-API-Key` header or a `?key=` query parameter.
            Leave unset (the default, `None`) and StayPresent generates a
            random key itself for this process's lifetime and logs it
            (at INFO level) so the admin view still works without you
            having to think about a key at all - pass a fixed string
            yourself if you want a key that survives a restart, or pass
            `api_key=""` to disable the admin view for this page entirely.
        trust_proxy_headers: If True, admin-login rate limiting (see
            `api_key` above) uses the client IP from the `X-Forwarded-For`
            header instead of the raw TCP connection. Only enable this if
            a reverse proxy you control is guaranteed to sit in front of
            every request and sets/overwrites this header itself -
            otherwise a client can forge it to pin a lockout on someone
            else's IP. Leave this False (the default) for a bare
            deployment with nothing in front of it; enabling it there
            would let anyone bypass rate limiting entirely by simply
            sending their own `X-Forwarded-For` header.
        mode: Color scheme for the status page - one of "light", "dark",
            or "auto" (default), same meaning as `markdown()`'s `mode`.
            "auto" follows the visitor's OS/browser preference via
            `prefers-color-scheme`; "light"/"dark" force that scheme
            regardless of the visitor's own setting.
        favicon: Optional favicon for the status page. A direct URL
            (starting with "http://", "https://", "//", or "data:") is
            used as-is; anything else (e.g. "favicon.png") is used as a
            plain href, so it must already be servable from somewhere
            (e.g. a path you've also registered with `html()`) - unlike
            `markdown()`'s `favicon`, there's no file directory of its
            own for a status page to resolve a local filename against.
            Leave unset and the page keeps its default behavior: a small
            dot favicon that updates live to reflect overall status
            (green/amber/red). Setting `favicon` replaces that dot with
            your own icon and disables the live color-swapping.
        description: Optional page description, added as both a standard
            `<meta name="description">` tag and an Open Graph description
            tag - useful for link-preview cards on social media/chat
            apps. Defaults to a generic "<title> - live status, powered
            by StayPresent." description when not given.
        poll_seconds: How often (in seconds) an open status page polls
            its own live data endpoint for updates. Defaults to 15.
            Must be a positive number - lower values mean fresher data
            at the cost of more requests against this endpoint from
            every open tab; higher values reduce that load at the cost
            of visitors seeing slightly staler data between polls.
        status: Whether this status page itself gets its own row *on*
            the status page (i.e. "Status - Web", alongside any other
            visible routes). Defaults to False, same as every other
            `staypresent.web.*()` route - the page working and being
            reachable is entirely independent of this; it only affects
            whether it also lists itself as a row on itself. Pass
            `status=True` if you want it to.

    Raises:
        TypeError: if `title`/`copyright`/`api_key`/`favicon`/
            `description` isn't a str or None, if `trust_proxy_headers`
            isn't a bool, if `footer_links` (or an entry within it) has
            the wrong shape, if `poll_seconds` isn't an int or float, or
            if `status` isn't a bool.
        ValueError: if `mode` isn't "light", "dark", or "auto", or if
            `poll_seconds` isn't positive.
    """
    status = _validate_status_param(status, "staypresent.web.status()")
    for name, value in (
        ("title", title), ("copyright", copyright), ("api_key", api_key),
        ("favicon", favicon), ("description", description),
    ):
        if value is not None and not isinstance(value, str):
            raise TypeError(f"staypresent.web.status(): '{name}' must be a str or None, got {type(value).__name__}.")
    if not isinstance(trust_proxy_headers, bool):
        raise TypeError(
            "staypresent.web.status(): 'trust_proxy_headers' must be a bool, "
            f"got {type(trust_proxy_headers).__name__}."
        )
    if isinstance(poll_seconds, bool) or not isinstance(poll_seconds, (int, float)):
        raise TypeError(
            "staypresent.web.status(): 'poll_seconds' must be an int or float, "
            f"got {type(poll_seconds).__name__}."
        )
    if poll_seconds <= 0:
        raise ValueError(
            f"staypresent.web.status(): 'poll_seconds' must be positive, got {poll_seconds!r}."
        )

    if mode is None:
        mode = "auto"
    if not isinstance(mode, str) or mode.strip().lower() not in _VALID_MARKDOWN_MODES:
        raise ValueError(
            "staypresent.web.status(): 'mode' must be one of 'light', 'dark', or "
            f"'auto', got {mode!r}."
        )
    mode = mode.strip().lower()

    validated_links = _validate_footer_links(footer_links)

    p = _normalize_path(path)

    resolved_api_key = api_key
    if api_key is None:
        resolved_api_key = secrets.token_urlsafe(32)
        logger.info(
            "staypresent.web.status(): no api_key given for the status page at '%s' - "
            "generated a random session key so its admin view still works: %s "
            "(pass api_key=\"\" to disable the admin view instead, or api_key=... for "
            "a fixed key that survives a restart).",
            p, resolved_api_key,
        )

    with _lock:
        previous = _routes.get(p)
        _routes[p] = {
            "type": "status",
            "title": title or "Service Status",
            "copyright": copyright,
            "footer_links": validated_links,
            "api_key": resolved_api_key,
            "trust_proxy_headers": trust_proxy_headers,
            "mode": mode,
            "favicon": favicon,
            "description": description,
            "poll_seconds": poll_seconds,
            "status": status,
        }
    _warn_if_overwriting(p, previous, "status")


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


def _virtual_default_state(p: str) -> dict:
    """
    The state for one of StayPresent's *implicit* defaults - the status
    page at "/status", the "I'm Present" message at "/", or the
    {"status": "ok"} response at "/health" - when nothing has actually
    been registered at `p`. Returns None for any other unregistered path.
    Not itself a caller-safe return value (the status template in
    particular is mutable) - callers must copy it, the same as they
    already must for a real `_routes` entry.
    """
    if p == _DEFAULT_STATUS_PATH:
        return _default_status_state()
    return _BUILTIN_DEFAULT_RESPONSES.get(p)


def get(path: str = "/") -> dict:
    """
    Return the currently configured response state for `path` as a dict
    (e.g. {'type': 'json', 'value': {...}}, or with 'mode'/'favicon'/
    'title'/'description' keys too for a "markdown" entry), or an empty
    dict if nothing is registered there and `path` isn't one of
    StayPresent's own implicit defaults either.

    This includes those implicit defaults - the plain "I'm Present"
    message at "/", the status page StayPresent serves at "/status", and
    the {"status": "ok"} response at "/health" - even though none of them
    is a real entry in the internal route table until you explicitly
    register something there yourself. Without this, `get("/status")`
    would misreport nothing as being served at "/status" even while a
    real status page is actively responding to every request there.

    The returned dict (including a nested "value" dict/list for a "json"
    entry) is a deep copy - mutating it afterwards (e.g. `state =
    web.get(); state["value"]["x"] = 1`) does NOT change the live
    response, the same guarantee `json()` itself already makes for the
    object you pass *into* it. A shallow copy here would otherwise still
    share the same nested dict/list `json()` stored internally, letting a
    seemingly read-only `get()` call silently mutate what's actually
    served to the next request.
    """
    p = _normalize_path(path)
    with _lock:
        state = _routes.get(p)
    if state is not None:
        return copy.deepcopy(state)
    virtual = _virtual_default_state(p)
    return copy.deepcopy(virtual) if virtual is not None else {}


def get_all() -> dict:
    """
    Return every path currently hosting a response, including
    StayPresent's own implicit defaults ("/", "/status", and "/health")
    whenever they haven't been overridden by an explicit registration.
    Useful for debugging, testing, or building your own dashboard of what
    StayPresent is currently serving.

    Same deep-copy guarantee as `get()`: the returned dicts (including any
    nested "value" for a "json" entry) are independent of StayPresent's
    live, internal state.
    """
    with _lock:
        result = {p: copy.deepcopy(state) for p, state in _routes.items()}
    if _DEFAULT_STATUS_PATH not in result:
        result[_DEFAULT_STATUS_PATH] = _default_status_state()
    for p, default_state in _BUILTIN_DEFAULT_RESPONSES.items():
        if p not in result:
            result[p] = copy.deepcopy(default_state)
    return result


def paths() -> list:
    """
    Return a sorted list of every path currently hosting a response,
    including StayPresent's own implicit defaults ("/", "/status", and
    "/health") whenever they haven't been overridden by an explicit
    registration.
    """
    with _lock:
        registered = set(_routes.keys())
    registered.add(_DEFAULT_STATUS_PATH)
    registered.update(_BUILTIN_DEFAULT_RESPONSES.keys())
    return sorted(registered)