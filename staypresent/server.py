"""
StayPresent - Flask Server

The shared Flask app StayPresent runs in the background: serves
whatever's registered via staypresent.web, renders HTML/Markdown
files fresh on every request, serves neighboring static assets, and
falls back to a built-in "/health" endpoint.

Part of the StayPresent project.
Docs: https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.md
"""

# Created and maintained by Ashish Sharma (Stay Elite).
# Copyright (c) 2026 Ashish Sharma (Stay Elite)
# Licensed under the MIT License. See the LICENSE file for details.

import hmac
import html as _html_escape
import logging
import os
import re
import threading
import time

from flask import Flask, Response, abort, jsonify, redirect, request, send_from_directory
from werkzeug.exceptions import NotFound

from . import web
from . import status_registry
from .markdown_renderer import render as _render_markdown
from .markdown_css import STAYPRESENT_MARKDOWN_CSS
from .status_assets import STATUS_CSS, STATUS_HTML_TEMPLATE, STATUS_JS

logger = logging.getLogger("staypresent")

# Admin-login rate limiting (see _status_admin_authorized below): tracks
# recent failed X-API-Key/?key= attempts per client IP, so a wrong key
# can only be tried _ADMIN_MAX_ATTEMPTS times before that IP is locked
# out for a while - without this, the status page's admin login would be
# open to unlimited brute-force guessing (hmac.compare_digest protects
# against timing attacks, not volume). This is process-local, in-memory
# state: it resets on restart and isn't shared across multiple server
# processes - adequate for the zero-config, single-process deployments
# StayPresent targets, not a substitute for a real auth layer in front of
# a larger deployment.
#
# Keyed by IP, so this only actually rate-limits per client if the IP
# StayPresent sees is the real client IP - behind a reverse proxy, that's
# only true when `trust_proxy_headers=True` was passed to
# `staypresent.web.status()` (see _client_ip below); otherwise every
# request looks like it comes from the proxy itself, and one wrong guess
# from any single visitor would lock out every legitimate admin behind
# that same proxy.
_admin_attempts_lock = threading.Lock()
_admin_failed_attempts = {}  # ip -> list of failure timestamps
_ADMIN_MAX_ATTEMPTS = 5
_ADMIN_LOCKOUT_SECONDS = 15 * 60

# static_folder=None disables Flask's own built-in "/static/<path:filename>"
# route. StayPresent doesn't ship any static assets of its own - but if left
# enabled, that built-in route silently shadows our own catch-all route below
# for any request path starting with "static/", which is the single most
# common naming convention for an assets folder (e.g. an HTML file that links
# to "static/style.css" or "static/logo.png" right next to it). With the
# built-in route active, those requests 404 against Flask's nonexistent
# default static folder instead of ever reaching catch_all(), which knows how
# to correctly serve them from next to the user's HTML/Markdown file.
app = Flask(__name__, static_folder=None)


def _render_html_file(file_path: str) -> Response:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return Response(content, mimetype="text/html")


def _render_markdown_file(
    file_path: str,
    mode: str = "auto",
    favicon: str = None,
    title: str = None,
    description: str = None,
) -> Response:
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    body = _render_markdown(source)

    # mode="dark" / "light" forces that color scheme regardless of the
    # visitor's OS/browser preference; "auto" (the default) follows it.
    mode = (mode or "auto").strip().lower()
    if mode not in ("light", "dark", "auto"):
        mode = "auto"
    theme_attr = "" if mode == "auto" else f' data-theme="{mode}"'
    color_scheme = "light dark" if mode == "auto" else mode

    page_title = title if title else os.path.basename(file_path)
    head_extra = []
    if favicon:
        # A direct URL (http(s)://, //) is used as-is; anything else is
        # treated as a path relative to this file's own directory, resolved
        # the exact same way neighboring assets (CSS, images) referenced
        # from inside an html()/markdown() file already are.
        head_extra.append(f'<link rel="icon" href="{_html_escape.escape(favicon, quote=True)}">')
    if description:
        esc_description = _html_escape.escape(description, quote=True)
        head_extra.append(f'<meta name="description" content="{esc_description}">')
        head_extra.append(f'<meta property="og:description" content="{esc_description}">')
    if title:
        head_extra.append(f'<meta property="og:title" content="{_html_escape.escape(title, quote=True)}">')

    page = (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<title>{_html_escape.escape(page_title)}</title>\n"
        f"<meta name=\"color-scheme\" content=\"{color_scheme}\">\n"
        + "".join(tag + "\n" for tag in head_extra)
        + f"<style>{STAYPRESENT_MARKDOWN_CSS}</style>\n"
        "</head>\n"
        f"<body><article class=\"markdown-body\"{theme_attr}>{body}</article></body>\n"
        "</html>"
    )
    return Response(page, mimetype="text/html")


def _status_base_path(route_path: str) -> str:
    """The route's own path prefix for its sub-resources: an empty string for the root path (so "" + "/assets/status.css" == "/assets/status.css"), or the route path itself otherwise (e.g. "/dashboard" + "/assets/status.css")."""
    return "" if route_path == "/" else route_path


# STATUS_CSS and STATUS_JS are byte-identical for every status page on a
# site - unlike the live data endpoint, neither one depends on which
# route it's serving (STATUS_JS works this out at runtime from its own
# page's URL - see status_assets.py). So, unlike the data endpoint, they
# are served from one fixed, shared URL rather than a URL scoped under
# each route - letting a browser (or a CDN in front of the app) cache
# and reuse a single fetch across every status page on the site instead
# of re-downloading the same ~24KB of CSS once per page. The "__" prefix
# keeps this out of the way of any path a person might reasonably
# register themselves.
_SHARED_STATUS_CSS_PATH = "/__staypresent__/status.css"
_SHARED_STATUS_JS_PATH = "/__staypresent__/status.js"


# staypresent.web.status() is entirely optional - "/status" serves this
# by default (with every field at its default) whenever nothing else is
# registered there, the same way "/health" (and the plain "I'm Present"
# message at "/") already fall back to their own built-ins. Not a real
# entry in web._routes, so registering your own response at "/status" is
# never reported as "overwriting" this - but web.get()/get_all()/paths()
# do surface it, the same way they surface "/health"'s and "/"'s
# defaults, since all three are genuinely being served. See
# web._default_status_state()/_BUILTIN_DEFAULT_RESPONSES/_DEFAULT_STATUS_PATH.


def _admin_rate_limited(ip: str) -> bool:
    """True if this IP has failed the admin key too many times recently
    and should be locked out regardless of what key it supplies next."""
    now = time.time()
    with _admin_attempts_lock:
        attempts = [t for t in _admin_failed_attempts.get(ip, []) if now - t < _ADMIN_LOCKOUT_SECONDS]
        if attempts:
            _admin_failed_attempts[ip] = attempts
        else:
            # Nothing left worth remembering for this IP (every past
            # failure has aged out of the lockout window) - drop the key
            # entirely instead of leaving an empty list sitting here
            # forever. Without this, every distinct IP that ever mistyped
            # the admin key even once would occupy a permanent entry in
            # this dict for the life of the process - unbounded growth
            # for an attacker (or simply many visitors) trying wrong keys
            # over time.
            _admin_failed_attempts.pop(ip, None)
        return len(attempts) >= _ADMIN_MAX_ATTEMPTS


def _record_admin_failure(ip: str) -> None:
    with _admin_attempts_lock:
        _admin_failed_attempts.setdefault(ip, []).append(time.time())


def _clear_admin_failures(ip: str) -> None:
    with _admin_attempts_lock:
        _admin_failed_attempts.pop(ip, None)


def _client_ip(state: dict) -> str:
    """
    The client IP used to key admin-login rate limiting (see
    _admin_rate_limited above). Defaults to the direct TCP peer
    (`request.remote_addr`) - correct for StayPresent running with
    nothing in front of it, but WRONG behind a reverse proxy (nginx,
    Cloudflare, most real deployments): every visitor there shares the
    proxy's own IP, so a single visitor's wrong guess would lock out
    every legitimate admin behind that same proxy.

    Only consults the client-supplied `X-Forwarded-For` header when
    `trust_proxy_headers=True` was explicitly passed to
    `staypresent.web.status()` - do this only when a reverse proxy you
    control is guaranteed to sit in front of every request (and to set
    or overwrite this header itself), since otherwise a client could
    simply forge its own `X-Forwarded-For` to pin the blame - and the
    resulting lockout - on someone else's IP instead of its own.
    """
    if state.get("trust_proxy_headers"):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # The header is a comma-separated, left-to-right chain with
            # the original client first and each proxy hop appending its
            # own address after - only the first entry is the actual
            # client; trusting a later one would trust whatever a
            # malicious client itself prepended.
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    return request.remote_addr or "unknown"


def _status_admin_authorized(state: dict) -> bool:
    """
    True if this status page has an api_key configured AND the request
    supplies the matching one, via an 'X-API-Key' header or a '?key='
    query parameter.

    Unlike an api_key anywhere else in StayPresent, this never blocks
    access to anything - the status page itself, and its CSS/JS/data
    endpoint, are always visible to everyone, the same way a real,
    professional status page's overall up/down state is public by design.
    All this controls is whether the *data* endpoint includes additional
    technical incident detail (the actual exit code behind a crash) that
    isn't meaningful or appropriate for a public audience - see
    `status_registry.snapshot()`'s `admin` argument. No api_key configured
    at all means that extra detail is never included for anyone, not that
    it's included for everyone.

    Failed attempts are rate-limited per client IP (see
    _admin_rate_limited above) - after _ADMIN_MAX_ATTEMPTS wrong keys
    within _ADMIN_LOCKOUT_SECONDS, further attempts from that IP are
    rejected outright (without even comparing the key) until the lockout
    window passes.
    """
    api_key = state.get("api_key")
    if not api_key:
        return False
    # Checked before touching the rate limiter: a request with no key
    # attempt at all isn't an "attempt" to rate-limit in the first place,
    # and this is by far the common case - the status page polls this
    # endpoint every STAYPRESENT_POLL_MS from every open tab, and the
    # overwhelming majority of visitors never touch the admin login at
    # all. Checking for a provided key first means that most-common,
    # highest-frequency path never has to take _admin_attempts_lock or
    # touch _admin_failed_attempts at all - only a request that actually
    # supplies a key (right or wrong) does.
    provided = request.headers.get("X-API-Key") or request.args.get("key")
    if not provided:
        return False
    ip = _client_ip(state)
    if _admin_rate_limited(ip):
        return False
    # hmac.compare_digest instead of "==": a plain string comparison
    # short-circuits at the first mismatched character, so the time it
    # takes to reject a wrong key leaks information about how many
    # leading characters were actually correct - a classic timing side
    # channel an attacker can use to recover the real key one character
    # at a time. compare_digest runs in constant time regardless of
    # where (or whether) the strings differ.
    if hmac.compare_digest(provided, api_key):
        _clear_admin_failures(ip)
        return True
    _record_admin_failure(ip)
    return False


def _render_status_page(state: dict, route_path: str) -> Response:
    # mode="dark" / "light" forces that color scheme regardless of the
    # visitor's OS/browser preference; "auto" (the default) follows it -
    # same convention as _render_markdown_file() above.
    mode = (state.get("mode") or "auto").strip().lower()
    if mode not in ("light", "dark", "auto"):
        mode = "auto"
    theme_attr = "" if mode == "auto" else f' data-theme="{mode}"'
    color_scheme = "light dark" if mode == "auto" else mode

    custom_favicon = state.get("favicon")
    if custom_favicon:
        # A caller-supplied favicon replaces the default live status dot
        # outright, and the JS is told (via this flag) to leave it alone -
        # otherwise the very next poll (see updateFavicon() in the JS)
        # would silently overwrite it with the colored dot again.
        favicon_url = _html_escape.escape(custom_favicon, quote=True)
        favicon_script = "<script>window.STAYPRESENT_CUSTOM_FAVICON = true;</script>"
    else:
        # A neutral grey dot until the page's own JS knows the real status
        # (its first fetch swaps this for a green/amber/red one - see
        # updateFavicon() in the JS) - self-contained inline SVG, so
        # there's no extra file to serve (or accidentally exclude) for
        # this.
        favicon_url = (
            "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
            "%3Ccircle cx='16' cy='16' r='14' fill='%23999999'/%3E%3C/svg%3E"
        )
        favicon_script = ""

    description = state.get("description") or f'{state["title"]} - live status, powered by StayPresent.'
    esc_description = _html_escape.escape(description, quote=True)
    og_tags = [f'<meta property="og:title" content="{_html_escape.escape(state["title"], quote=True)}">']
    og_tags.append(f'<meta property="og:description" content="{esc_description}">')

    if state.get("copyright"):
        year = time.strftime("%Y")
        copyright_block = f'        <p>&copy; {year} {_html_escape.escape(state["copyright"])}</p>'
    else:
        # Omitted entirely (not even an empty <p>) rather than shown with a
        # generic default - a copyright line StayPresent invented on the
        # person's behalf would be worse than none at all.
        copyright_block = ""

    links = state.get("footer_links") or []
    if links:
        link_html = " | ".join(
            f'<a href="{_html_escape.escape(link["url"], quote=True)}">{_html_escape.escape(link["label"])}</a>'
            for link in links
        )
        footer_links_block = f'        <div class="footer-links">\n          {link_html}\n        </div>'
    else:
        footer_links_block = ""

    # Every value above is substituted for its placeholder in a single
    # pass over the *original* STATUS_HTML_TEMPLATE (via one combined
    # regex, below) rather than via a chain of sequential str.replace()
    # calls against the page as it's progressively rewritten. Sequential
    # whole-string replace() is not safe here: each call re-scans the
    # *entire* page, including text substituted in by an earlier call in
    # the chain - so a caller-supplied value that happens to contain
    # another placeholder's literal token (e.g. a status-page `title` of
    # "__STAYPRESENT_CSS_URL__") would silently get overwritten by that
    # later replace() call instead of appearing verbatim, corrupting the
    # page in a way that's very easy to miss (there's no error - it just
    # renders someone else's value in the wrong place). A single regex
    # pass over the untouched template has no such risk: re.sub() never
    # rescans text it has just inserted, so a value can contain any of
    # these tokens (or the substitution's own regex-special characters -
    # re.sub()'s replacement function returns them as a literal string,
    # never reinterpreted as a pattern) without affecting anything else.
    replacements = {
        "__STAYPRESENT_TITLE__": _html_escape.escape(state["title"]),
        "__STAYPRESENT_CSS_URL__": _SHARED_STATUS_CSS_PATH,
        "__STAYPRESENT_JS_URL__": _SHARED_STATUS_JS_PATH,
        "__STAYPRESENT_THEME_ATTR__": theme_attr,
        "__STAYPRESENT_COLOR_SCHEME__": color_scheme,
        "__STAYPRESENT_FAVICON_URL__": favicon_url,
        "__STAYPRESENT_FAVICON_SCRIPT__": favicon_script,
        "__STAYPRESENT_DESCRIPTION__": esc_description,
        "__STAYPRESENT_OG_TAGS_BLOCK__": "\n    ".join(og_tags),
        "__STAYPRESENT_COPYRIGHT_BLOCK__": copyright_block,
        "__STAYPRESENT_FOOTER_LINKS_BLOCK__": footer_links_block,
    }
    pattern = re.compile("|".join(re.escape(token) for token in replacements))
    page = pattern.sub(lambda m: replacements[m.group(0)], STATUS_HTML_TEMPLATE)

    return Response(page, mimetype="text/html")


_FALSY_QUERY_VALUES = {"0", "false", "no", "off", ""}


def _query_flag(name: str) -> bool:
    """
    Parse a query-string flag (e.g. "?history=1") as an actual boolean,
    rather than Python's "any non-empty string is truthy" - which would
    otherwise mean "?history=0" (or "=false"/"=no"/"=off") *enables* the
    thing it looks like it's disabling, since request.args.get(name)
    returns the literal string "0", and `if "0":` is True. Missing
    entirely, or any of the values above (case-insensitively), is
    treated as False; anything else (typically "1"/"true"/"yes", but
    genuinely any other non-empty value) is treated as True - the same
    permissive-but-not-backwards convention most query-flag APIs use.
    """
    value = request.args.get(name)
    if value is None:
        return False
    return value.strip().lower() not in _FALSY_QUERY_VALUES


def _render_status_data(state: dict) -> Response:
    admin = _status_admin_authorized(state)
    # ?history=1 asks for the expanded incident list (up to
    # status_registry._MAX_INCIDENTS_HISTORY) instead of the default
    # recent-activity view - see the status page's "view full history"
    # toggle in status_assets.py.
    incident_limit = None
    if _query_flag("history"):
        incident_limit = status_registry._MAX_INCIDENTS_HISTORY
    data = status_registry.snapshot(admin=admin, incident_limit=incident_limit)
    # Whether an admin login is even worth showing on this page - NOT the
    # api_key itself. The real key must never appear in a response served
    # to every visitor (that's the whole page/CSS/JS/data endpoint now -
    # none of them require it to load) - only a human admin typing it into
    # the page's own login field, kept client-side from that point on,
    # ever supplies it. This lives in the data response (rather than being
    # templated into the JS, as it used to be) precisely so the JS itself
    # can be one static, shared asset - see _SHARED_STATUS_JS_PATH above.
    data["admin_available"] = bool(state.get("api_key"))
    # Same reasoning as admin_available above: this is per-route
    # (staypresent.web.status()'s own poll_seconds=), so it's carried in
    # the data response rather than templated into STATUS_JS, keeping
    # that file one static, shared asset across every status page on the
    # site - see _SHARED_STATUS_JS_PATH above. The JS falls back to its
    # own 15s default until this first response arrives, then adopts
    # whatever this route configured.
    data["poll_seconds"] = state.get("poll_seconds", 15)
    return jsonify(data)


def _render_response(state: dict, route_path: str = None):
    response_type = state.get("type")
    value = state.get("value")

    if response_type == "html":
        try:
            return _render_html_file(value)
        except (OSError, UnicodeDecodeError) as exc:
            return jsonify({"error": f"Could not read HTML file: {exc}"}), 500

    if response_type == "markdown":
        try:
            return _render_markdown_file(
                value,
                mode=state.get("mode", "auto"),
                favicon=state.get("favicon"),
                title=state.get("title"),
                description=state.get("description"),
            )
        except (OSError, UnicodeDecodeError) as exc:
            return jsonify({"error": f"Could not read Markdown file: {exc}"}), 500

    if response_type == "status":
        return _render_status_page(state, route_path)

    if response_type == "json":
        try:
            return jsonify(value)
        except TypeError as exc:
            return jsonify({"error": f"Could not serialize JSON response: {exc}"}), 500

    if response_type == "text":
        return Response(str(value), mimetype="text/plain")

    # Fallback for any unexpected/legacy state shape.
    if isinstance(value, (dict, list)):
        return jsonify(value)
    return str(value)


def _find_status_data_route(request_path: str):
    """
    Match a request against a "status"-type route's own live data endpoint
    ("<route>/api/status.json") - the one sub-resource that's genuinely
    per-route, since each status page can have its own `api_key` (the
    services display-name/description overrides, by contrast, are
    process-wide now - see staypresent.web.html()/json()/text()/
    markdown()'s own services_name/services_description). The CSS and JS
    sub-resources are no longer per-route (see
    _SHARED_STATUS_CSS_PATH/_SHARED_STATUS_JS_PATH above, handled
    directly in catch_all instead).

    `web.get_all()` surfaces the *default* status page implicitly active
    at "/status" the same as any explicitly-registered one (see
    `web._default_status_state()`), so no separate fallback is needed
    here for it.
    """
    for route_path, state in web.get_all().items():
        if state.get("type") != "status":
            continue
        base = _status_base_path(route_path)
        if request_path == base + "/api/status.json":
            return state

    return None


def _find_asset_owner(request_path: str):
    best = None  # (prefix_len, directory, remainder)
    # Collected across every html()/markdown() route sharing a directory,
    # not just whichever one "wins" the prefix match below - see
    # web._normalize_exclude()'s docstring for why this has to be a union:
    # a security-relevant exclusion set by any one route serving out of a
    # directory should apply to every request resolving to that directory,
    # not depend on which specific route happened to have the longest
    # matching prefix.
    exclude_by_directory = {}
    for route_path, state in web.get_all().items():
        if state.get("type") not in ("html", "markdown"):
            continue

        prefix = "/" if route_path == "/" else route_path + "/"
        directory = os.path.dirname(state["value"])
        if state.get("exclude"):
            exclude_by_directory.setdefault(directory, set()).update(state["exclude"])

        if request_path == route_path or not request_path.startswith(prefix):
            continue

        remainder = request_path[len(prefix):]
        if best is None or len(prefix) > best[0]:
            best = (len(prefix), directory, remainder)

    if best is None:
        return None
    _, directory, remainder = best
    if web._path_excluded(remainder, exclude_by_directory.get(directory)):
        return None
    return directory, remainder


@app.route("/", defaults={"req_path": ""})
@app.route("/<path:req_path>")
def catch_all(req_path):
    request_path = re.sub(r"/+", "/", "/" + req_path)
    had_trailing_slash = request_path != "/" and request_path.endswith("/")
    canonical = request_path.rstrip("/") if request_path != "/" else "/"
    if not canonical:
        canonical = "/"

    # StayPresent's own status-page CSS/JS live at these two fixed,
    # shared URLs regardless of which route(s) actually host a status
    # page - see _SHARED_STATUS_CSS_PATH/_SHARED_STATUS_JS_PATH above.
    if canonical == _SHARED_STATUS_CSS_PATH:
        return Response(STATUS_CSS, mimetype="text/css")
    if canonical == _SHARED_STATUS_JS_PATH:
        return Response(STATUS_JS, mimetype="application/javascript")

    # web.get() already returns StayPresent's own implicit defaults for
    # "/" (a plain "I'm Present" message), "/status" (the built-in status
    # page), and "/health" ({"status": "ok"}) whenever nothing has been
    # explicitly registered at those paths, so no separate fallback is
    # needed for any of them here.
    state = web.get(canonical)

    if state:
        response_type = state.get("type")
        if response_type in ("html", "markdown", "status") and canonical != "/" and not had_trailing_slash:
            # Redirect "/dashboard" -> "/dashboard/" so relative asset links
            # inside the served file (e.g. href="style.css") resolve against
            # this page's own directory instead of its parent. Preserve any
            # query string (e.g. "/dashboard?tab=2") - dropping it here would
            # silently lose it on the very first request to a fresh path.
            target = canonical + "/"
            if request.query_string:
                target += "?" + request.query_string.decode("utf-8", "replace")
            return redirect(target, code=308)
        return _render_response(state, canonical)

    owner = _find_asset_owner(canonical)
    if owner is not None:
        directory, remainder = owner
        if not remainder:
            abort(404)
        try:
            # send_from_directory safely resolves `remainder` against
            # `directory` and refuses to serve anything that escapes it
            # (no path traversal).
            return send_from_directory(directory, remainder)
        except NotFound:
            abort(404)

    status_state = _find_status_data_route(canonical)
    if status_state is not None:
        return _render_status_data(status_state)

    abort(404)