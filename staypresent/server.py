import html as _html_escape
import logging
import os
import re

from flask import Flask, Response, abort, jsonify, redirect, send_from_directory
from werkzeug.exceptions import NotFound

from . import web
from .markdown_renderer import render as _render_markdown
from .markdown_css import STAYPRESENT_MARKDOWN_CSS

logger = logging.getLogger("staypresent")

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


def _render_markdown_file(file_path: str) -> Response:
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    body = _render_markdown(source)

    page = (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<title>{_html_escape.escape(os.path.basename(file_path))}</title>\n"
        "<meta name=\"color-scheme\" content=\"light dark\">\n"
        f"<style>{STAYPRESENT_MARKDOWN_CSS}</style>\n"
        "</head>\n"
        f"<body><article class=\"markdown-body\">{body}</article></body>\n"
        "</html>"
    )
    return Response(page, mimetype="text/html")


def _render_response(state: dict):
    response_type = state.get("type")
    value = state.get("value")

    if response_type == "html":
        try:
            return _render_html_file(value)
        except (OSError, UnicodeDecodeError) as exc:
            return jsonify({"error": f"Could not read HTML file: {exc}"}), 500

    if response_type == "markdown":
        try:
            return _render_markdown_file(value)
        except (OSError, UnicodeDecodeError) as exc:
            return jsonify({"error": f"Could not read Markdown file: {exc}"}), 500

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


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


def _find_asset_owner(request_path: str):
    best = None  # (prefix_len, directory, remainder)
    for route_path, state in web.get_all().items():
        if state.get("type") not in ("html", "markdown"):
            continue

        prefix = "/" if route_path == "/" else route_path + "/"
        if request_path == route_path or not request_path.startswith(prefix):
            continue

        remainder = request_path[len(prefix):]
        if best is None or len(prefix) > best[0]:
            best = (len(prefix), os.path.dirname(state["value"]), remainder)

    if best is None:
        return None
    return best[1], best[2]


@app.route("/", defaults={"req_path": ""})
@app.route("/<path:req_path>")
def catch_all(req_path):
    request_path = re.sub(r"/+", "/", "/" + req_path)
    had_trailing_slash = request_path != "/" and request_path.endswith("/")
    canonical = request_path.rstrip("/") if request_path != "/" else "/"
    if not canonical:
        canonical = "/"

    state = web.get(canonical)
    if state:
        response_type = state.get("type")
        if response_type in ("html", "markdown") and canonical != "/" and not had_trailing_slash:
            # Redirect "/dashboard" -> "/dashboard/" so relative asset links
            # inside the served file (e.g. href="style.css") resolve against
            # this page's own directory instead of its parent.
            return redirect(canonical + "/", code=308)
        return _render_response(state)

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

    abort(404)