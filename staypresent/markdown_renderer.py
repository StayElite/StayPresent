"""
StayPresent Markdown-to-HTML Renderer.
"""

import html
import re

__all__ = ["render", "MarkdownRenderer"]

# ---------------------------------------------------------------------------
# Block-level patterns
# ---------------------------------------------------------------------------

_ATX_HEADING_RE = re.compile(r'^ {0,3}(#{1,6})(?:\s+(.*?))?\s*#*\s*$')
_SETEXT_H1_RE = re.compile(r'^ {0,3}=+\s*$')
_SETEXT_H2_RE = re.compile(r'^ {0,3}-+\s*$')
_HR_RE = re.compile(r'^ {0,3}((-[ \t]*){3,}|(\*[ \t]*){3,}|(_[ \t]*){3,})$')
_FENCE_RE = re.compile(r'^ {0,3}(`{3,}|~{3,})[ \t]*([^\s`~]*)[ \t]*$')
_BLOCKQUOTE_RE = re.compile(r'^ {0,3}>[ ]?(.*)$')
_UL_RE = re.compile(r'^( *)([-*+])[ \t]+(.*)$')
_OL_RE = re.compile(r'^( *)(\d{1,9})[.)][ \t]+(.*)$')
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
_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^\s)]+)(?:\s+"([^"]*)")?\)')
_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^\s)]+)(?:\s+"([^"]*)")?\)')
_AUTOLINK_RE = re.compile(r'&lt;((?:https?|ftp)://[^\s&]+)&gt;')
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


class MarkdownRenderer:
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

            # --- setext heading (Text\n=== or Text\n---) ---
            if (
                line.strip()
                and not _UL_RE.match(line)
                and not _OL_RE.match(line)
                and not _BLOCKQUOTE_RE.match(line)
                and i + 1 < n
            ):
                if _SETEXT_H1_RE.match(lines[i + 1]):
                    out.append(self._render_heading(1, line.strip()))
                    i += 2
                    continue
                if _SETEXT_H2_RE.match(lines[i + 1]) and lines[i + 1].strip("- \t"):
                    out.append(self._render_heading(2, line.strip()))
                    i += 2
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
                    if marker_re.match(lines[i]) or (
                        list_lines
                        and (lines[i].startswith(" ") or lines[i].startswith("\t") or not lines[i].strip())
                        and not self._is_block_start(lines[i])
                    ):
                        list_lines.append(lines[i])
                        i += 1
                    else:
                        break
                while list_lines and not list_lines[-1].strip():
                    list_lines.pop()
                out.append(self._render_list(list_lines, ordered))
                continue

            # --- paragraph ---
            para_lines = [line]
            i += 1
            while i < n and lines[i].strip() and not self._is_block_start(lines[i]):
                if i + 1 < n and (_SETEXT_H1_RE.match(lines[i]) or _SETEXT_H2_RE.match(lines[i])):
                    break
                para_lines.append(lines[i])
                i += 1
            joined = "\n".join(para_lines)
            out.append("<p>{}</p>".format(self._render_inline(joined)))

        return "\n".join(out)

    # -- lists ------------------------------------------------------------

    def _render_list(self, lines, ordered):
        marker_re = _OL_RE if ordered else _UL_RE
        items = []  # list of (indent, [content_lines])
        i, n = 0, len(lines)

        while i < n:
            line = lines[i]
            m = marker_re.match(line)
            if not m:
                if items:
                    items[-1][1].append(line)
                i += 1
                continue
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

        tag = "ol" if ordered else "ul"
        parts = ["<{}>".format(tag)]
        for _, item_lines in items:
            parts.append("<li>{}</li>".format(self._render_list_item(item_lines)))
        parts.append("</{}>".format(tag))
        return "\n".join(parts)

    def _render_list_item(self, item_lines):
        while item_lines and not item_lines[0].strip():
            item_lines = item_lines[1:]
        while item_lines and not item_lines[-1].strip():
            item_lines = item_lines[:-1]
        text = "\n".join(item_lines)
        has_blank = any(not l.strip() for l in item_lines)
        starts_nested_list = bool(item_lines) and (_UL_RE.match(item_lines[0]) or _OL_RE.match(item_lines[0]))
        if not has_blank and not starts_nested_list and "\n" not in text.strip("\n"):
            return self._render_inline(text)
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
        plain = re.sub(r'`([^`]*)`', r'\1', text)  # drop inline-code backticks
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

    def _stash(self, rendered_html):
        key = "\x00{}\x00".format(len(self._placeholders))
        self._placeholders.append(rendered_html)
        return key

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
            title_attr = ' title="{}"'.format(html.escape(title)) if title else ""
            return self._stash(
                '<img src="{}" alt="{}"{}>'.format(html.escape(url, quote=True), html.escape(alt, quote=True), title_attr)
            )

        text = _IMAGE_RE.sub(_image, text)

        # 5. links
        def _link(m):
            label, url, title = m.group(1), m.group(2), m.group(3)
            title_attr = ' title="{}"'.format(html.escape(title)) if title else ""
            return self._stash('<a href="{}"{}>{}</a>'.format(html.escape(url, quote=True), title_attr, label))

        text = _LINK_RE.sub(_link, text)

        # 6. autolinks
        def _autolink(m):
            url = m.group(1)
            return self._stash('<a href="{0}">{0}</a>'.format(html.escape(url, quote=True)))

        text = _AUTOLINK_RE.sub(_autolink, text)

        # 7. emphasis / strikethrough
        text = _BOLD_ITALIC_RE.sub(r'<strong><em>\2</em></strong>', text)
        text = _BOLD_RE.sub(r'<strong>\2</strong>', text)
        text = _ITALIC_STAR_RE.sub(r'<em>\1</em>', text)
        text = _ITALIC_UNDER_RE.sub(r'<em>\1</em>', text)
        text = _STRIKE_RE.sub(r'<del>\1</del>', text)

        # 8. hard line breaks
        text = _HARDBREAK_RE.sub('<br>\n', text)

        # 9. restore protected fragments
        for idx, val in enumerate(self._placeholders):
            text = text.replace("\x00{}\x00".format(idx), val)

        self._placeholders = None
        return text


def render(source: str) -> str:
    """Render a Markdown document to an HTML fragment (no <html>/<body> wrapper)."""
    return MarkdownRenderer().render(source)