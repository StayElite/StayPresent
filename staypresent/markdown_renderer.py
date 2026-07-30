"""
StayPresent Markdown Renderer

A fast, dependency-free Markdown-to-HTML renderer used by
staypresent.web.markdown() - headings, emphasis, links, images,
lists, tables, code fences, blockquotes, and raw HTML passthrough,
with GitHub-style heading slugs.

Part of the StayPresent project.
Docs: https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.md
"""

# Created and maintained by Ashish Sharma (Stay Elite).
# Copyright (c) 2026 Ashish Sharma (Stay Elite)
# Licensed under the MIT License. See the LICENSE file for details.

import html
import re

__all__ = ["render", "StayPresentMarkdownRenderer"]

# ---------------------------------------------------------------------------
# Block-level patterns
# ---------------------------------------------------------------------------

_ATX_HEADING_RE = re.compile(r'^ {0,3}(#{1,6})(?:\s+(.*?))?\s*#*\s*$')
_SETEXT_H1_RE = re.compile(r'^ {0,3}=+\s*$')
_SETEXT_H2_RE = re.compile(r'^ {0,3}-+\s*$')
_HR_RE = re.compile(r'^ {0,3}((-[ \t]*){3,}|(\*[ \t]*){3,}|(_[ \t]*){3,})$')
_FENCE_RE = re.compile(r'^ {0,3}(`{3,}|~{3,})[ \t]*([^\s`~]*)(?:[ \t].*)?$')
_BLOCKQUOTE_RE = re.compile(r'^ {0,3}>[ ]?(.*)$')
_UL_RE = re.compile(r'^( *)([-*+])[ \t]+(.*)$')
_OL_RE = re.compile(r'^( *)(\d{1,9})[.)][ \t]+(.*)$')
# GitHub-Flavored-Markdown task list items: "- [ ] todo" / "- [x] done" (case-
# insensitive "x"). Matched against a list item's own first content line
# (after its "-"/"*"/"1." marker has already been stripped), so this only
# ever fires on the very start of an item, matching GitHub's own behavior -
# "- [ ]" mid-sentence isn't a checkbox.
_TASK_ITEM_RE = re.compile(r'^\[([ xX])\](?:\s+(.*)|$)')
_TABLE_SEP_RE = re.compile(r'^ {0,3}\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$')
_INDENTED_CODE_RE = re.compile(r'^(?: {4}|\t)(.*)$')

# Raw HTML blocks: a line starting (after up to 3 spaces) with an opening or
# closing tag whose name is a known block-level element is passed through
# verbatim (unescaped, unprocessed) until the next blank line - the same
# "HTML block" behavior CommonMark/GitHub use for things like centered
# badges/logos (`<p align="center"><img ...></p>`) sitting in a MARKDOWN.
_HTML_BLOCK_START_RE = re.compile(r'^ {0,3}</?([a-zA-Z][a-zA-Z0-9-]*)(?:[ \t>/]|$)')
_HTML_COMMENT_START_RE = re.compile(r'^ {0,3}<!--')
_HTML_BLOCK_TAGS = frozenset({
    "address", "article", "aside", "base", "basefont", "blockquote", "body",
    "caption", "center", "col", "colgroup", "dd", "details", "dialog", "dir",
    "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form",
    "frame", "frameset", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header",
    "hr", "html", "iframe", "legend", "li", "link", "main", "menu",
    "menuitem", "nav", "noframes", "ol", "optgroup", "option", "p", "param",
    "section", "summary", "table", "tbody", "td", "tfoot", "th", "thead",
    "title", "tr", "track", "ul", "script", "style", "pre", "textarea",
    "img", "a", "span", "button", "input", "label", "select", "svg",
})

# ---------------------------------------------------------------------------
# Inline-level patterns
# ---------------------------------------------------------------------------

_CODE_SPAN_RE = re.compile(r'(`+)(.+?)\1')
_ESCAPE_RE = re.compile(r'\\([\\`*_{}\[\]()#+.!>~|<>&-])')
# A link/image destination normally can't contain a bare ")" (that's what
# marks the end of the "(url)" part) - except CommonMark itself allows one
# level of *balanced* parens inside the destination (e.g. the very common
# Wikipedia-style "https://en.wikipedia.org/wiki/Foo_(bar)"), so this
# matches either a run of non-space, non-paren characters, or a fully
# self-contained "(...)" group with no spaces/parens inside it - repeated.
# Without the second alternative, that Wikipedia URL's own closing ")"
# would be mistaken for the *link's* closing ")", truncating the URL right
# before "bar)" and leaving a stray, dangling ")" in the rendered output.
_LINK_DEST = r'(?:[^\s()]|\([^\s()]*\))+'
_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\((' + _LINK_DEST + r')(?:\s+"([^"]*)")?\)')
_LINK_RE = re.compile(r'\[([^\]]+)\]\((' + _LINK_DEST + r')(?:\s+"([^"]*)")?\)')
# Non-greedy up to the closing "&gt;": the text these run against has
# already been through the whole-line html.escape() in step 3 of
# _render_inline, so a literal "&" in the original URL (e.g. a query
# string's "?a=1&b=2") shows up here as the *sequence* "&amp;", which
# still contains a literal "&" character. Excluding "&" from the captured
# run (as a naive "stop at any bare ampersand" character class would)
# truncates the URL right at that entity. Matching non-greedily up to the
# next "&gt;" instead captures the whole (already-escaped) URL.
_AUTOLINK_RE = re.compile(r'&lt;((?:https?|ftp)://\S+?)&gt;')
_BOLD_ITALIC_RE = re.compile(r'(\*\*\*|___)(?=\S)(.+?)(?<=\S)\1')
_BOLD_RE = re.compile(r'(\*\*|__)(?=\S)(.+?)(?<=\S)\1')
_ITALIC_STAR_RE = re.compile(r'(?<!\*)\*(?!\*)(?=\S)(.+?)(?<=\S)\*(?!\*)')
_ITALIC_UNDER_RE = re.compile(r'(?<![\w_])_(?!_)(?=\S)(.+?)(?<=\S)_(?![\w_])')
_STRIKE_RE = re.compile(r'~~(?=\S)(.+?)(?<=\S)~~')
_HARDBREAK_RE = re.compile(r'(?: {2,}|\\)\n')
# GitHub's own heading-slug algorithm: lowercase, drop anything that isn't a
# unicode word character, whitespace, or hyphen (this is what removes emoji
# and punctuation while leaving existing hyphens/underscores alone) - but
# deliberately keep variation-selector code points (U+FE00-U+FE0F), since
# GitHub's slugger does the same, and *every individual space* (not each
# run of whitespace) becomes its own hyphen, which is why an emoji-led
# heading like "🚀 Features" slugs to "-features" (leading hyphen) and
# "A & B" slugs to "a--b" (double hyphen, since removing "&" leaves two
# spaces behind).
_SLUG_STRIP_RE = re.compile(r'[^\w\s\-\uFE00-\uFE0F]', re.UNICODE)

# Used only to build heading slugs: strip Markdown *syntax* (not just inline
# code backticks) down to plain rendered text first, so a heading like
# "## [Link Text](https://example.com) Heading" slugs to "link-text-heading"
# - matching what GitHub's own slugger does with the *rendered* heading text
# - instead of "link-texthttpsexamplecom-heading" (the link's URL, punched
# straight through _SLUG_STRIP_RE's punctuation-stripping and fused onto the
# label, since a raw, un-stripped "[Link Text](https://example.com)" has no
# non-word characters removed from between the label and the URL other than
# the brackets/parens themselves).
_SLUG_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\([^)]*\)')
_SLUG_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]*\)')

# Schemes that a browser will treat as *executable* rather than merely
# "fetch this resource" - "javascript:"/"vbscript:" run arbitrary script
# directly, "data:" can smuggle a full HTML document (script and all) into
# an <a href>, and "file:" can leak local filesystem contents. Rejected for
# link hrefs; "data:" is left off the image list since data: *images*
# (data:image/png;base64,...) are common and inert - browsers don't execute
# script from an <img src>, even an SVG one.
_DANGEROUS_LINK_SCHEMES = frozenset({"javascript", "vbscript", "data", "file"})
_DANGEROUS_IMAGE_SCHEMES = frozenset({"javascript", "vbscript", "file"})
_URL_SCHEME_RE = re.compile(r'^\s*([a-zA-Z][a-zA-Z0-9+.\-]*):')


def _has_dangerous_scheme(url: str, dangerous_schemes: frozenset) -> bool:
    """
    True if `url` starts with one of `dangerous_schemes` (case-insensitively).
    A URL with no scheme at all (a relative path, "#anchor", "//host/path",
    etc.) is always safe by this check - only an explicit, *executable*
    scheme is rejected.
    """
    m = _URL_SCHEME_RE.match(url)
    return bool(m) and m.group(1).lower() in dangerous_schemes


class StayPresentMarkdownRenderer:
    """Stateful renderer (tracks heading-id uniqueness across one document)."""

    def __init__(self):
        self._used_ids = set()
        self._placeholders = None  # set per inline-render call

    # -- public API ---------------------------------------------------

    def render(self, source: str) -> str:
        source = source.replace("\r\n", "\n").replace("\r", "\n")
        lines = source.split("\n")
        return self._render_blocks(lines)

    # -- block parsing --------------------------------------------------

    def _is_html_block_start(self, line: str) -> bool:
        m = _HTML_BLOCK_START_RE.match(line)
        if not m:
            return False
        return m.group(1).lower() in _HTML_BLOCK_TAGS

    def _is_table_start(self, lines, i: int) -> bool:
        """True if lines[i] is a table header row (the same condition the
        top-level table branch below uses): a "|" on this line followed
        immediately by a delimiter row on the next line."""
        return (
            "|" in lines[i]
            and i + 1 < len(lines)
            and _TABLE_SEP_RE.match(lines[i + 1])
        )

    def _is_block_start(self, line: str) -> bool:
        return bool(
            _ATX_HEADING_RE.match(line)
            or _HR_RE.match(line)
            or _FENCE_RE.match(line)
            or _BLOCKQUOTE_RE.match(line)
            or _UL_RE.match(line)
            or _OL_RE.match(line)
            or _HTML_COMMENT_START_RE.match(line)
            or self._is_html_block_start(line)
        )

    def _render_blocks(self, lines):
        out = []
        i, n = 0, len(lines)

        while i < n:
            line = lines[i]

            if not line.strip():
                i += 1
                continue

            # --- raw HTML block (pass through verbatim, unescaped) ---
            if _HTML_COMMENT_START_RE.match(line) or self._is_html_block_start(line):
                html_lines = []
                while i < n and lines[i].strip():
                    html_lines.append(lines[i])
                    i += 1
                out.append("\n".join(html_lines))
                continue

            # --- fenced code block ---
            m = _FENCE_RE.match(line)
            if m:
                fence_char = m.group(1)[0]
                fence_len = len(m.group(1))
                lang = m.group(2)
                i += 1
                code_lines = []
                closing_re = re.compile(
                    r'^ {0,3}' + re.escape(fence_char) + '{' + str(fence_len) + ',}\\s*$'
                )
                while i < n and not closing_re.match(lines[i]):
                    code_lines.append(lines[i])
                    i += 1
                if i < n:
                    i += 1  # consume closing fence
                out.append(self._render_code_block("\n".join(code_lines), lang))
                continue

            # --- ATX heading ---
            m = _ATX_HEADING_RE.match(line)
            if m:
                level = len(m.group(1))
                text = (m.group(2) or "").strip()
                out.append(self._render_heading(level, text))
                i += 1
                continue

            # --- thematic break ---
            if _HR_RE.match(line):
                out.append("<hr>")
                i += 1
                continue

            # --- blockquote ---
            if _BLOCKQUOTE_RE.match(line):
                bq_lines = []
                while i < n:
                    m2 = _BLOCKQUOTE_RE.match(lines[i])
                    if not m2:
                        break
                    bq_lines.append(m2.group(1))
                    i += 1
                inner = self._render_blocks(bq_lines)
                out.append("<blockquote>\n{}\n</blockquote>".format(inner))
                continue

            # --- indented code block (4 spaces / tab) ---
            if _INDENTED_CODE_RE.match(line):
                code_lines = []
                while i < n:
                    if not lines[i].strip():
                        code_lines.append("")
                        i += 1
                        continue
                    m3 = _INDENTED_CODE_RE.match(lines[i])
                    if not m3:
                        break
                    code_lines.append(m3.group(1))
                    i += 1
                while code_lines and not code_lines[-1].strip():
                    code_lines.pop()
                out.append(self._render_code_block("\n".join(code_lines), ""))
                continue

            # --- table ---
            if "|" in line and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1]):
                table_lines = [line, lines[i + 1]]
                i += 2
                while i < n and lines[i].strip() and "|" in lines[i]:
                    table_lines.append(lines[i])
                    i += 1
                out.append(self._render_table(table_lines))
                continue

            # --- list (ordered / unordered) ---
            if _UL_RE.match(line) or _OL_RE.match(line):
                ordered = bool(_OL_RE.match(line))
                marker_re = _OL_RE if ordered else _UL_RE
                list_lines = []
                while i < n:
                    # Any indented line is potentially nested content
                    # belonging to the current list item - a fenced code
                    # block, a blockquote, a heading, or a sub-list of
                    # either marker type (e.g. "1. Run this:\n   ```bash\n
                    # ...\n   ```\n2. Next step", a very common
                    # step-by-step-instructions pattern). Whether it's
                    # actually indented *enough* to belong to the item (vs.
                    # a fresh, unrelated top-level block) is exactly what
                    # _render_list()'s own per-item indentation comparison
                    # below decides - this collection pass only needs to
                    # gather candidate lines, not pre-judge them by
                    # pattern-matching what kind of block they look like.
                    # Using _is_block_start() to end the list here (as this
                    # used to) meant *any* recognized block-start pattern -
                    # not just an unindented, genuinely new one - ended the
                    # list immediately, breaking every one of those nested
                    # cases apart into disconnected sibling blocks.
                    if marker_re.match(lines[i]) or (
                        list_lines
                        and (lines[i].startswith(" ") or lines[i].startswith("\t") or not lines[i].strip())
                    ):
                        list_lines.append(lines[i])
                        i += 1
                    else:
                        break
                while list_lines and not list_lines[-1].strip():
                    list_lines.pop()
                out.append(self._render_list(list_lines, ordered))
                continue

            # --- paragraph (a trailing "==="/"---" underline converts the
            # whole run collected so far into a setext heading instead of
            # literal paragraph text - checked before _is_block_start() so
            # a "---" underline isn't instead swallowed as an unrelated
            # thematic break) ---
            para_lines = [line]
            i += 1
            while i < n and lines[i].strip():
                if _SETEXT_H1_RE.match(lines[i]) or _SETEXT_H2_RE.match(lines[i]):
                    break
                if self._is_block_start(lines[i]):
                    break
                # A table header row directly following paragraph text (no
                # blank line) still starts its own table block, matching
                # GFM - it isn't covered by _is_block_start() above, whose
                # checks are all single-line and can't see the delimiter
                # row on the *next* line that's what actually makes this a
                # table. Without this, `intro line\n| a | b |\n|---|---|`
                # got swallowed whole as literal paragraph text instead of
                # rendering a table, since the table branch above only
                # triggers when a table is the very first thing at the top
                # of the block loop.
                if self._is_table_start(lines, i):
                    break
                para_lines.append(lines[i])
                i += 1

            if i < n and _SETEXT_H1_RE.match(lines[i]):
                out.append(self._render_heading(1, "\n".join(para_lines).strip()))
                i += 1
                continue
            if i < n and _SETEXT_H2_RE.match(lines[i]):
                out.append(self._render_heading(2, "\n".join(para_lines).strip()))
                i += 1
                continue

            joined = "\n".join(para_lines)
            out.append("<p>{}</p>".format(self._render_inline(joined)))

        return "\n".join(out)

    # -- lists ------------------------------------------------------------

    def _render_list(self, lines, ordered):
        marker_re = _OL_RE if ordered else _UL_RE
        items = []  # list of (indent, [content_lines])
        i, n = 0, len(lines)

        start_number = None
        while i < n:
            line = lines[i]
            m = marker_re.match(line)
            if not m:
                if items:
                    items[-1][1].append(line)
                i += 1
                continue
            if ordered and start_number is None:
                # Only the very first item's number matters for numbering -
                # HTML's <ol start> sets where the list *begins*; every
                # subsequent <li> simply increments from there regardless
                # of what number the author wrote next to it.
                start_number = int(m.group(2))
            indent = len(m.group(1))
            content = m.group(3)
            prefix_len = len(m.group(0)) - len(content)
            item_lines = [content]
            i += 1
            while i < n:
                nxt = lines[i]
                if not nxt.strip():
                    if i + 1 < n and (len(lines[i + 1]) - len(lines[i + 1].lstrip())) >= prefix_len and lines[i + 1].strip():
                        item_lines.append("")
                        i += 1
                        continue
                    break
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent >= prefix_len:
                    item_lines.append(nxt[prefix_len:])
                    i += 1
                    continue
                break
            items.append((indent, item_lines))

        # A list is "loose" (GFM/CommonMark terminology) - every item's text
        # wrapped in <p> - as soon as *any* item is separated from another
        # by a blank line, not just the item(s) directly touching that
        # blank line.
        list_is_loose = any(any(not l.strip() for l in item_lines) for _, item_lines in items)

        tag = "ol" if ordered else "ul"
        start_attr = " start=\"{}\"".format(start_number) if ordered and start_number not in (None, 1) else ""
        parts = ["<{}{}>".format(tag, start_attr)]
        for _, item_lines in items:
            task_match = _TASK_ITEM_RE.match(item_lines[0]) if item_lines else None
            if task_match is not None:
                checked = task_match.group(1).lower() == "x"
                item_lines = [task_match.group(2) or ""] + item_lines[1:]
                checkbox = '<input type="checkbox" checked disabled> ' if checked else '<input type="checkbox" disabled> '
                parts.append(
                    '<li class="task-list-item">{}{}</li>'.format(
                        checkbox, self._render_list_item(item_lines, list_is_loose)
                    )
                )
            else:
                parts.append("<li>{}</li>".format(self._render_list_item(item_lines, list_is_loose)))
        parts.append("</{}>".format(tag))
        return "\n".join(parts)

    def _render_list_item(self, item_lines, list_is_loose=False):
        while item_lines and not item_lines[0].strip():
            item_lines = item_lines[1:]
        while item_lines and not item_lines[-1].strip():
            item_lines = item_lines[:-1]
        if not item_lines:
            return ""

        text = "\n".join(item_lines)
        starts_nested_list = bool(_UL_RE.match(item_lines[0]) or _OL_RE.match(item_lines[0]))
        if not list_is_loose and not starts_nested_list and "\n" not in text.strip("\n"):
            return self._render_inline(text)

        if not list_is_loose and not starts_nested_list:
            # Split off this item's own leading paragraph text from a
            # nested sub-list that follows it directly (no blank line) -
            # rendering just that leading run inline (no <p>) keeps a tight
            # item like "item 2\n  - nested" from picking up an unwanted
            # <p> around "item 2" purely because render_blocks() below
            # would otherwise treat the whole thing as block-level content.
            split_at = next(
                (idx for idx in range(1, len(item_lines))
                 if _UL_RE.match(item_lines[idx]) or _OL_RE.match(item_lines[idx])),
                None,
            )
            if split_at is not None:
                leading = "\n".join(item_lines[:split_at])
                rest = self._render_blocks(item_lines[split_at:])
                return "{}\n{}".format(self._render_inline(leading), rest)

        return self._render_blocks(item_lines)

    # -- tables -------------------------------------------------------------

    def _split_table_row(self, line):
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|") and not line.endswith("\\|"):
            line = line[:-1]
        cells = re.split(r'(?<!\\)\|', line)
        return [c.replace("\\|", "|").strip() for c in cells]

    def _render_table(self, lines):
        header = self._split_table_row(lines[0])
        aligns_raw = self._split_table_row(lines[1])
        aligns = []
        for c in aligns_raw:
            left, right = c.startswith(":"), c.endswith(":")
            if left and right:
                aligns.append("center")
            elif right:
                aligns.append("right")
            elif left:
                aligns.append("left")
            else:
                aligns.append(None)

        def style_for(idx):
            if idx < len(aligns) and aligns[idx]:
                return ' style="text-align:{}"'.format(aligns[idx])
            return ""

        out = ["<table>", "<thead>", "<tr>"]
        for idx, cell in enumerate(header):
            out.append("<th{}>{}</th>".format(style_for(idx), self._render_inline(cell)))
        out.append("</tr>")
        out.append("</thead>")
        out.append("<tbody>")
        for row in lines[2:]:
            cells = self._split_table_row(row)
            out.append("<tr>")
            for idx in range(len(header)):
                cell = cells[idx] if idx < len(cells) else ""
                out.append("<td{}>{}</td>".format(style_for(idx), self._render_inline(cell)))
            out.append("</tr>")
        out.append("</tbody>")
        out.append("</table>")
        return "\n".join(out)

    # -- headings -------------------------------------------------------------

    def _slugify(self, text):
        plain = _SLUG_IMAGE_RE.sub(r'\1', text)  # ![alt](url) -> alt
        plain = _SLUG_LINK_RE.sub(r'\1', plain)  # [label](url) -> label
        plain = re.sub(r'`([^`]*)`', r'\1', plain)  # drop inline-code backticks
        # Unwrap emphasis/bold/strikethrough markers the same way - a heading
        # like "## **Bold** Heading" should slug to "bold-heading", not carry
        # literal asterisks through into "bold-heading" by accident of them
        # already being non-word characters _SLUG_STRIP_RE strips anyway
        # (harmless here), but this also correctly unwraps single-* / single-_
        # italics and ~~strikethrough~~, which _SLUG_STRIP_RE alone cannot
        # distinguish from ordinary stray punctuation.
        plain = _BOLD_ITALIC_RE.sub(r'\2', plain)
        plain = _BOLD_RE.sub(r'\2', plain)
        plain = _ITALIC_STAR_RE.sub(r'\1', plain)
        plain = _ITALIC_UNDER_RE.sub(r'\1', plain)
        plain = _STRIKE_RE.sub(r'\1', plain)
        plain = plain.lower()
        plain = _SLUG_STRIP_RE.sub("", plain)
        # Every individual whitespace character becomes its own hyphen -
        # deliberately NOT collapsed, and NOT trimmed from the ends, to
        # match GitHub's own slugs (see _SLUG_STRIP_RE comment above).
        slug = re.sub(r'\s', '-', plain)
        if not slug:
            slug = "section"
        base, suffix = slug, 0
        while slug in self._used_ids:
            suffix += 1
            slug = "{}-{}".format(base, suffix)
        self._used_ids.add(slug)
        return slug

    def _render_heading(self, level, text):
        slug = self._slugify(text)
        return '<h{0} id="{1}">{2}</h{0}>'.format(level, slug, self._render_inline(text))

    # -- code blocks -------------------------------------------------------------

    def _render_code_block(self, code, lang):
        cls = ' class="language-{}"'.format(html.escape(lang)) if lang else ""
        return "<pre><code{}>{}</code></pre>".format(cls, html.escape(code))

    # -- inline rendering -------------------------------------------------------------

    @staticmethod
    def _escape_attr_quotes(s):
        """
        Escape a fragment for safe use inside an HTML attribute, given that
        it was captured (via _IMAGE_RE/_LINK_RE/_AUTOLINK_RE) from text that
        has *already* been through the whole-line `html.escape(text,
        quote=False)` call earlier in `_render_inline` - so `&`, `<`, `>`
        are already entity-escaped. Only literal `"` still needs escaping;
        running the fragment through `html.escape()` again here would
        double-escape those already-escaped entities (e.g. turning a URL's
        `&b=2` into `&amp;amp;b=2`).
        """
        return s.replace('"', "&quot;")

    def _stash(self, rendered_html):
        key = "\x00{}\x00".format(len(self._placeholders))
        self._placeholders.append(rendered_html)
        return key

    @staticmethod
    def _apply_emphasis(text):
        """Run bold/italic/strikethrough substitution over a fragment of text."""
        text = _BOLD_ITALIC_RE.sub(r'<strong><em>\2</em></strong>', text)
        text = _BOLD_RE.sub(r'<strong>\2</strong>', text)
        text = _ITALIC_STAR_RE.sub(r'<em>\1</em>', text)
        text = _ITALIC_UNDER_RE.sub(r'<em>\1</em>', text)
        text = _STRIKE_RE.sub(r'<del>\1</del>', text)
        return text

    def _render_inline(self, text):
        text = text.strip()
        self._placeholders = []

        # 1. code spans (protected from further processing)
        def _code_span(m):
            return self._stash("<code>{}</code>".format(html.escape(m.group(2).strip())))

        text = _CODE_SPAN_RE.sub(_code_span, text)

        # 2. backslash-escaped punctuation (protected too)
        def _escaped(m):
            return self._stash(html.escape(m.group(1)))

        text = _ESCAPE_RE.sub(_escaped, text)

        # 3. escape remaining raw text
        text = html.escape(text, quote=False)

        # 4. images
        def _image(m):
            alt, url, title = m.group(1), m.group(2), m.group(3)
            if _has_dangerous_scheme(url, _DANGEROUS_IMAGE_SCHEMES):
                # Don't emit an <img> pointing at a script-executing/local-
                # file URL scheme - fall back to just the (already-escaped)
                # alt text, the same way a browser shows alt text for any
                # image it couldn't load.
                return self._stash(alt)
            # alt/url/title were captured from text already run through
            # html.escape(..., quote=False) in step 3 above - only quotes
            # need escaping here, not the whole fragment again.
            title_attr = ' title="{}"'.format(self._escape_attr_quotes(title)) if title else ""
            return self._stash(
                '<img src="{}" alt="{}"{}>'.format(
                    self._escape_attr_quotes(url), self._escape_attr_quotes(alt), title_attr
                )
            )

        text = _IMAGE_RE.sub(_image, text)

        # 5. links
        def _link(m):
            label, url, title = m.group(1), m.group(2), m.group(3)
            # Same reasoning as _image above: url/title are already
            # entity-escaped from step 3, so only quotes need handling here.
            # `label` is rendered as element content, not an attribute, so
            # it's already correctly single-escaped - but it still needs to
            # go through emphasis/bold/strikethrough processing itself: the
            # main text's step 7 (below) never sees this label, since by
            # the time step 7 runs, the whole `<a href="...">...</a>` this
            # closure returns has already been stashed as a single opaque
            # placeholder token. Without this, "[**bold link**](url)" would
            # render literal "**" asterisks instead of <strong> markup.
            label = self._apply_emphasis(label)
            if _has_dangerous_scheme(url, _DANGEROUS_LINK_SCHEMES):
                # Don't linkify a script-executing/document-smuggling/local-
                # file URL scheme - render the (already emphasis-processed)
                # label as plain text instead of wrapping it in an <a>.
                return self._stash(label)
            title_attr = ' title="{}"'.format(self._escape_attr_quotes(title)) if title else ""
            return self._stash('<a href="{}"{}>{}</a>'.format(self._escape_attr_quotes(url), title_attr, label))

        text = _LINK_RE.sub(_link, text)

        # 6. autolinks
        def _autolink(m):
            url = m.group(1)
            # url is already entity-escaped (captured from post-step-3 text
            # via the non-greedy _AUTOLINK_RE above) - only quotes remain.
            return self._stash('<a href="{0}">{0}</a>'.format(self._escape_attr_quotes(url)))

        text = _AUTOLINK_RE.sub(_autolink, text)

        # 7. emphasis / strikethrough
        text = self._apply_emphasis(text)

        # 8. hard line breaks
        text = _HARDBREAK_RE.sub('<br>\n', text)

        # 9. restore protected fragments
        #
        # Restore in reverse (highest index first), not forward order. A
        # stash can only ever contain a *lower*-index placeholder nested
        # inside it (it was created earlier in the pipeline - e.g. a code
        # span's placeholder gets embedded inside a link's stashed
        # `<a>...</a>` HTML when the code span is part of the link text).
        # Restoring forward (0 -> N) means a low-index token trapped inside
        # a higher-index link's stashed string never gets a chance to
        # resolve, since its own turn already passed before the link
        # unwraps it - the placeholder leaks straight into the page as raw
        # "\x000\x00" text. Restoring highest-index-first guarantees any
        # nested token is exposed in `text` before its own turn comes up.
        for idx in range(len(self._placeholders) - 1, -1, -1):
            text = text.replace("\x00{}\x00".format(idx), self._placeholders[idx])

        self._placeholders = None
        return text


def render(source: str) -> str:
    """Render a Markdown document to an HTML fragment (no <html>/<body> wrapper)."""
    return StayPresentMarkdownRenderer().render(source)