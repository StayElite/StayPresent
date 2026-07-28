"""
CSS stylesheet used to style StayPresent's Markdown-rendered HTML output.
"""

STAYPRESENT_MARKDOWN_CSS = r'''
/*
 *
 * A close approximation of GitHub's own ".markdown-body" stylesheet,
 * for use with staypresent's built-in Markdown renderer
 * (staypresent.markdown_renderer.render). Supports both light and dark modes
 * automatically via prefers-color-scheme.
 *
 * Usage:
 *   <link rel="stylesheet" href="github-markdown.css">
 *   <article class="markdown-body">
 *     ...rendered HTML from staypresent.markdown_renderer.render()...
 *   </article>
 */

.markdown-body {
  --color-canvas-default: #ffffff;
  --color-canvas-subtle: #f6f8fa;
  --color-fg-default: #1f2328;
  --color-fg-muted: #59636e;
  --color-fg-subtle: #6e7781;
  --color-border-default: #d1d9e0;
  --color-border-muted: #d1d9e0b3;
  --color-neutral-muted: #818b981f;
  --color-accent-fg: #0969da;
  --color-accent-emphasis: #0969da;
  --color-success-fg: #1a7f37;
  --color-danger-fg: #d1242f;
  --color-attention-fg: #9a6700;
  --color-attention-subtle: #fff8c5;
  --color-danger-subtle: #ffebe9;
  --color-done-fg: #8250df;

  color: var(--color-fg-default);
  background-color: var(--color-canvas-default);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans",
    Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  font-size: 16px;
  line-height: 1.5;
  word-wrap: break-word;
  max-width: 980px;
  margin: 0 auto;
  padding: 32px;
}

@media (prefers-color-scheme: dark) {
  .markdown-body {
    --color-canvas-default: #0d1117;
    --color-canvas-subtle: #161b22;
    --color-fg-default: #e6edf3;
    --color-fg-muted: #848d97;
    --color-fg-subtle: #6e7681;
    --color-border-default: #3d444d;
    --color-border-muted: #3d444db3;
    --color-neutral-muted: #6e768166;
    --color-accent-fg: #4493f8;
    --color-accent-emphasis: #1f6feb;
    --color-success-fg: #3fb950;
    --color-danger-fg: #f85149;
    --color-attention-fg: #d29922;
    --color-attention-subtle: #bb800926;
    --color-danger-subtle: #f8514926;
    --color-done-fg: #ab7df8;
  }
}

.markdown-body[data-theme="light"] {
  color-scheme: light;
  --color-canvas-default: #ffffff;
  --color-canvas-subtle: #f6f8fa;
  --color-fg-default: #1f2328;
  --color-fg-muted: #59636e;
  --color-fg-subtle: #6e7781;
  --color-border-default: #d1d9e0;
  --color-border-muted: #d1d9e0b3;
  --color-neutral-muted: #818b981f;
  --color-accent-fg: #0969da;
  --color-accent-emphasis: #0969da;
  --color-success-fg: #1a7f37;
  --color-danger-fg: #d1242f;
  --color-attention-fg: #9a6700;
  --color-attention-subtle: #fff8c5;
  --color-danger-subtle: #ffebe9;
  --color-done-fg: #8250df;
}

.markdown-body[data-theme="dark"] {
  color-scheme: dark;
  --color-canvas-default: #0d1117;
  --color-canvas-subtle: #161b22;
  --color-fg-default: #e6edf3;
  --color-fg-muted: #848d97;
  --color-fg-subtle: #6e7681;
  --color-border-default: #3d444d;
  --color-border-muted: #3d444db3;
  --color-neutral-muted: #6e768166;
  --color-accent-fg: #4493f8;
  --color-accent-emphasis: #1f6feb;
  --color-success-fg: #3fb950;
  --color-danger-fg: #f85149;
  --color-attention-fg: #d29922;
  --color-attention-subtle: #bb800926;
  --color-danger-subtle: #f8514926;
  --color-done-fg: #ab7df8;
}

@media (max-width: 767px) {
  .markdown-body {
    padding: 16px;
  }
}

.markdown-body::before {
  display: table;
  content: "";
}

.markdown-body::after {
  display: table;
  clear: both;
  content: "";
}

/* ---- Headings ---- */

.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4,
.markdown-body h5,
.markdown-body h6 {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.25;
}

.markdown-body h1 {
  padding-bottom: 0.3em;
  font-size: 2em;
  border-bottom: 1px solid var(--color-border-muted);
}

.markdown-body h2 {
  padding-bottom: 0.3em;
  font-size: 1.5em;
  border-bottom: 1px solid var(--color-border-muted);
}

.markdown-body h3 {
  font-size: 1.25em;
}

.markdown-body h4 {
  font-size: 1em;
}

.markdown-body h5 {
  font-size: 0.875em;
}

.markdown-body h6 {
  font-size: 0.85em;
  color: var(--color-fg-muted);
}

.markdown-body h1[align="center"],
.markdown-body h2[align="center"],
.markdown-body h3[align="center"] {
  border-bottom: none;
  padding-bottom: 0;
}

/* Anchor-link icon next to headings that have an id (like GitHub's own
   "#" hover link) - purely decorative, shows on hover only. */
.markdown-body h1[id]:hover .anchor,
.markdown-body h2[id]:hover .anchor,
.markdown-body h3[id]:hover .anchor,
.markdown-body h4[id]:hover .anchor,
.markdown-body h5[id]:hover .anchor,
.markdown-body h6[id]:hover .anchor {
  opacity: 1;
}

.markdown-body .anchor {
  float: left;
  margin-left: -20px;
  padding-right: 4px;
  opacity: 0;
  text-decoration: none;
}

/* ---- Paragraphs, lists, general spacing ---- */

.markdown-body p,
.markdown-body blockquote,
.markdown-body ul,
.markdown-body ol,
.markdown-body dl,
.markdown-body table,
.markdown-body pre,
.markdown-body details {
  margin-top: 0;
  margin-bottom: 16px;
}

.markdown-body ul,
.markdown-body ol {
  padding-left: 2em;
}

.markdown-body ul ul,
.markdown-body ul ol,
.markdown-body ol ol,
.markdown-body ol ul {
  margin-top: 0;
  margin-bottom: 0;
}

.markdown-body li {
  word-wrap: break-all;
}

.markdown-body li > p {
  margin-top: 16px;
}

.markdown-body li + li {
  margin-top: 0.25em;
}

.markdown-body dl {
  padding: 0;
}

.markdown-body dl dt {
  padding: 0;
  margin-top: 16px;
  font-size: 1em;
  font-style: italic;
  font-weight: 600;
}

.markdown-body dl dd {
  padding: 0 16px;
  margin-bottom: 16px;
}

/* ---- Links ---- */

.markdown-body a {
  color: var(--color-accent-fg);
  text-decoration: none;
  background-color: transparent;
}

.markdown-body a:hover {
  text-decoration: underline;
}

.markdown-body a:not([href]) {
  color: inherit;
  text-decoration: none;
}

/* ---- Emphasis ---- */

.markdown-body strong {
  font-weight: 600;
}

.markdown-body em {
  font-style: italic;
}

.markdown-body del {
  text-decoration: line-through;
}

/* ---- Images ---- */

.markdown-body img {
  max-width: 100%;
  box-sizing: content-box;
  background-color: var(--color-canvas-default);
  border-style: none;
  vertical-align: middle;
}

/* ---- Horizontal rule ---- */

.markdown-body hr {
  height: 0.25em;
  padding: 0;
  margin: 24px 0;
  background-color: var(--color-border-default);
  border: 0;
}

/* ---- Blockquotes ---- */

.markdown-body blockquote {
  padding: 0 1em;
  color: var(--color-fg-muted);
  border-left: 0.25em solid var(--color-border-default);
}

.markdown-body blockquote > :first-child {
  margin-top: 0;
}

.markdown-body blockquote > :last-child {
  margin-bottom: 0;
}

.markdown-body blockquote > blockquote {
  margin-top: 16px;
}

/* ---- Tables ---- */

.markdown-body table {
  display: block;
  width: max-content;
  max-width: 100%;
  overflow: auto;
  border-spacing: 0;
  border-collapse: collapse;
}

.markdown-body table th {
  font-weight: 600;
}

.markdown-body table th,
.markdown-body table td {
  padding: 6px 13px;
  border: 1px solid var(--color-border-default);
}

.markdown-body table thead tr {
  background-color: var(--color-canvas-default);
}

.markdown-body table tr {
  background-color: var(--color-canvas-default);
  border-top: 1px solid var(--color-border-muted);
}

.markdown-body table tr:nth-child(2n) {
  background-color: var(--color-canvas-subtle);
}

.markdown-body table img {
  background-color: transparent;
}

/* ---- Inline code & fenced code blocks ---- */

.markdown-body code,
.markdown-body tt {
  padding: 0.2em 0.4em;
  margin: 0;
  font-size: 85%;
  white-space: break-spaces;
  background-color: var(--color-neutral-muted);
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
    "Liberation Mono", monospace;
}

.markdown-body pre {
  padding: 16px;
  overflow: auto;
  font-size: 85%;
  line-height: 1.45;
  color: var(--color-fg-default);
  background-color: var(--color-canvas-subtle);
  border-radius: 6px;
}

.markdown-body pre code,
.markdown-body pre tt {
  display: inline;
  max-width: auto;
  padding: 0;
  margin: 0;
  overflow: visible;
  line-height: inherit;
  word-wrap: normal;
  background-color: transparent;
  border: 0;
  font-size: 100%;
  white-space: pre;
}

/* Minimal, generic syntax-highlight-ish accents for the
   `class="language-xxx"` hook staypresent's renderer adds to fenced code
   blocks. Not real tokenization - just a restrained set of GitHub-ish
   accent colors so code doesn't look completely flat. */
.markdown-body pre code.language-diff .line,
.markdown-body pre code[class*="language-"] {
  color: inherit;
}

/* ---- Details / summary ---- */

.markdown-body details summary {
  cursor: pointer;
}

.markdown-body details:not([open]) > *:not(summary) {
  display: none;
}

/* ---- Kbd ---- */

.markdown-body kbd {
  display: inline-block;
  padding: 3px 5px;
  font: 11px ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
    monospace;
  line-height: 10px;
  color: var(--color-fg-default);
  vertical-align: middle;
  background-color: var(--color-canvas-subtle);
  border: solid 1px var(--color-border-default);
  border-bottom-color: var(--color-border-default);
  border-radius: 6px;
  box-shadow: inset 0 -1px 0 var(--color-border-default);
}

/* ---- Centered badge/logo header blocks (raw HTML passthrough) ---- */

.markdown-body p[align="center"] {
  margin-bottom: 8px;
}

.markdown-body p[align="center"] img {
  margin: 0 2px;
}

'''