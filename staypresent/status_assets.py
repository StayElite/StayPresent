"""
StayPresent - Status Page Assets

The CSS, HTML shell, and client-side JS for staypresent.web.status()'s
built-in status page. Embedded as string constants (the same pattern
markdown_css.py already uses) rather than shipped as separate files, so
no packaging/MANIFEST changes are needed to include them in the wheel.

Part of the StayPresent project.
Docs: https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.md
"""

# Created and maintained by Ashish Sharma (Stay Elite).
# Copyright (c) 2026 Ashish Sharma (Stay Elite)
# Licensed under the MIT License. See the LICENSE file for details.

STATUS_CSS = """* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  --primary-color: #f63b3b;
  --primary-dark: #eb2525;
  --primary-light: #fa6060;
  --success-color: #10b981;
  --warning-color: #f59e0b;
  --danger-color: #ef4444;
  --dark: #0f172a;
  --dark-secondary: #1e293b;
  --text-secondary: #334155;
  --light: #f8fafc;
  --light-secondary: #f1f5f9;
  --gray: #64748b;
  --gray-light: #94a3b8;
  --white: #ffffff;
  --border-color: #e2e8f0;
  --border-hover: #cbd5e1;
  --badge-op-bg: #ecfdf5;
  --badge-op-fg: #065f46;
  --badge-op-border: #a7f3d0;
  --badge-deg-bg: #fffbeb;
  --badge-deg-fg: #92400e;
  --badge-deg-border: #fde68a;
  --badge-off-bg: #fef2f2;
  --badge-off-fg: #991b1b;
  --badge-off-border: #fecaca;
  --warn-bg: #fffbeb;
  --warn-border: #fde68a;
  --warn-fg: #92400e;
}

/* Dark-mode variable overrides, driven by staypresent.web.status()'s
   `mode` - "auto" (no data-theme attribute) follows the visitor's OS/
   browser preference via prefers-color-scheme; "dark"/"light" force it
   via [data-theme] regardless of that preference. Same convention as
   markdown_css.py's .markdown-body theming. Every rule below reads one
   of these variables rather than a literal color, so this block is the
   only place a dark palette needs to be defined. */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --dark: #e6edf3;
    --dark-secondary: var(--border-hover);
    --text-secondary: #cbd5e1;
    --light: #0b1220;
    --light-secondary: #1e293b;
    --gray: #94a3b8;
    --gray-light: #64748b;
    --white: #16202f;
    --border-color: #2d3b4e;
    --border-hover: #3d4f68;
    --badge-op-bg: rgba(16, 185, 129, 0.15);
    --badge-op-fg: #6ee7b7;
    --badge-op-border: rgba(16, 185, 129, 0.35);
    --badge-deg-bg: rgba(245, 158, 11, 0.15);
    --badge-deg-fg: #fcd34d;
    --badge-deg-border: rgba(245, 158, 11, 0.35);
    --badge-off-bg: rgba(239, 68, 68, 0.15);
    --badge-off-fg: #fca5a5;
    --badge-off-border: rgba(239, 68, 68, 0.35);
    --warn-bg: rgba(245, 158, 11, 0.12);
    --warn-border: rgba(245, 158, 11, 0.35);
    --warn-fg: #fcd34d;
  }
}

:root[data-theme="dark"] {
  --dark: #e6edf3;
  --dark-secondary: var(--border-hover);
  --text-secondary: #cbd5e1;
  --light: #0b1220;
  --light-secondary: #1e293b;
  --gray: #94a3b8;
  --gray-light: #64748b;
  --white: #16202f;
  --border-color: #2d3b4e;
  --border-hover: #3d4f68;
  --badge-op-bg: rgba(16, 185, 129, 0.15);
  --badge-op-fg: #6ee7b7;
  --badge-op-border: rgba(16, 185, 129, 0.35);
  --badge-deg-bg: rgba(245, 158, 11, 0.15);
  --badge-deg-fg: #fcd34d;
  --badge-deg-border: rgba(245, 158, 11, 0.35);
  --badge-off-bg: rgba(239, 68, 68, 0.15);
  --badge-off-fg: #fca5a5;
  --badge-off-border: rgba(239, 68, 68, 0.35);
  --warn-bg: rgba(245, 158, 11, 0.12);
  --warn-border: rgba(245, 158, 11, 0.35);
  --warn-fg: #fcd34d;
}

:root[data-theme="light"] {
  --dark: #0f172a;
  --dark-secondary: #1e293b;
  --text-secondary: #334155;
  --light: #f8fafc;
  --light-secondary: #f1f5f9;
  --gray: #64748b;
  --gray-light: #94a3b8;
  --white: #ffffff;
  --border-color: #e2e8f0;
  --border-hover: #cbd5e1;
  --badge-op-bg: #ecfdf5;
  --badge-op-fg: #065f46;
  --badge-op-border: #a7f3d0;
  --badge-deg-bg: #fffbeb;
  --badge-deg-fg: #92400e;
  --badge-deg-border: #fde68a;
  --badge-off-bg: #fef2f2;
  --badge-off-fg: #991b1b;
  --badge-off-border: #fecaca;
  --warn-bg: #fffbeb;
  --warn-border: #fde68a;
  --warn-fg: #92400e;
}

html {
  scroll-behavior: smooth;
  color-scheme: light dark;
}

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background-color: var(--light);
  color: var(--dark);
  line-height: 1.6;
  min-height: 100vh;
}

.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 30px 20px;
}

/* Base Status Indicators */
.status-indicator {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 8px;
}

.status-indicator.operational { background-color: var(--success-color); box-shadow: 0 0 8px rgba(16, 185, 129, 0.5); }
.status-indicator.degraded { background-color: var(--warning-color); box-shadow: 0 0 8px rgba(245, 158, 11, 0.5); }
.status-indicator.offline { background-color: var(--danger-color); box-shadow: 0 0 8px rgba(239, 68, 68, 0.5); }
.status-indicator.resolved { background-color: var(--success-color); }
.status-indicator.investigating { background-color: var(--warning-color); }
.status-indicator.identified { background-color: var(--danger-color); }

/* Buttons */
.history-toggle {
  padding: 8px 16px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  background: var(--white);
  color: var(--text-secondary);
  font-size: 0.85em;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.history-toggle:hover {
  background: var(--light-secondary);
  border-color: var(--border-hover);
}

/* Header Redesign */
header {
  text-align: center;
  margin-bottom: 40px;
  padding: 40px 20px;
  background: var(--white);
  border-radius: 12px;
  border: 1px solid var(--border-color);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}

header h1 {
  font-size: clamp(1.8em, 4vw, 2.5em);
  color: var(--dark);
  margin-bottom: 8px;
  font-weight: 700;
  letter-spacing: -0.5px;
}

.subtitle {
  font-size: clamp(0.9em, 2vw, 1.05em);
  color: var(--gray);
  font-weight: 400;
}

/* Status Summary Redesign */
.status-summary {
  margin-bottom: 40px;
}

.summary-card {
  background: var(--white);
  padding: 24px 30px;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  border-left: 6px solid var(--primary-color);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}

.status-label {
  font-size: 0.85em;
  font-weight: 600;
  color: var(--gray);
  display: block;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.status-badge {
  padding: 6px 14px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 0.9em;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid transparent;
}

.badge-group {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.service-type-badge {
  padding: 3px 8px;
  border-radius: 4px;
  background: #94a3b8;
  color: var(--white);
  font-size: 0.8em;
  text-transform: uppercase;
  font-weight: 600;
  vertical-align: middle;
  letter-spacing: 0.5px;
  /* margin-left: 8px; -> removed */
}
.service-type-badge.web {
  background: #ff5c2d;
}

.status-badge.operational { background: var(--badge-op-bg); color: var(--badge-op-fg); border-color: var(--badge-op-border); }
.status-badge.degraded { background: var(--badge-deg-bg); color: var(--badge-deg-fg); border-color: var(--badge-deg-border); }
.status-badge.offline { background: var(--badge-off-bg); color: var(--badge-off-fg); border-color: var(--badge-off-border); }

.status-counts {
  margin-top: 8px;
  font-size: 0.85em;
  color: var(--gray);
}

.summary-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
}

.last-updated {
  color: var(--gray);
  font-size: 0.85em;
}

/* Section Headings */
.metrics h2, .services h2, .incidents h2 {
  font-size: 1.5em;
  margin-bottom: 24px;
  color: var(--dark);
  font-weight: 700;
  letter-spacing: -0.3px;
  display: flex;
  align-items: center;
  gap: 10px;
}

/* Metrics Section & Chart Redesign */
.metrics { margin-bottom: 50px; }
.metrics-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
}

.chart-container {
  background: var(--white);
  padding: 24px;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}

.chart-container h3 {
  font-size: 1.05em;
  color: var(--text-secondary);
  margin-bottom: 16px;
  font-weight: 600;
}

.chart-container canvas {
  max-height: 280px;
  width: 100% !important;
}

.service-filters {
  display: flex;
  gap: 12px;
  margin-bottom: 25px;
  flex-wrap: wrap;
}
.filter-btn {
  padding: 10px 22px;
  border: 2px solid var(--light-secondary);
  background: var(--white);
  border-radius: 25px;
  cursor: pointer;
  font-weight: 700;
  color: var(--gray);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  font-size: 0.9em;
  letter-spacing: 0.3px;
  text-transform: uppercase;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
}
.filter-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  transform: translateY(-2px);
  box-shadow: 0 5px 14px rgba(59, 130, 246, 0.15); /* Adjusted to match new primary */
}
.filter-btn.active {
  background: linear-gradient(135deg, var(--primary-color), var(--primary-dark));
  color: var(--white);
  border-color: transparent;
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.3); /* Adjusted to match new primary */
}
.service-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
}
.service-item {
  background: linear-gradient(135deg, var(--white) 0%, var(--light-secondary) 100%);
  padding: 24px;
  border-radius: 12px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.08);
  border-left: 5px solid var(--success-color);
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}
.service-item::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -10%;
  width: 180px;
  height: 180px;
  background: radial-gradient(circle, rgba(16, 185, 129, 0.08), transparent);
  border-radius: 50%;
  transition: all 0.6s ease;
  z-index: 0;
}
.service-item > * {
  position: relative;
  z-index: 1;
}
.service-item:hover {
  transform: translateY(-8px);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.12);
}
.service-item:hover::before {
  right: -5%;
  top: -25%;
}
.service-item.degraded {
  border-left-color: var(--warning-color);
}
.service-item.degraded::before {
  background: radial-gradient(circle, rgba(245, 158, 11, 0.08), transparent);
}
.service-item.offline {
  border-left-color: var(--danger-color);
}
.service-item.offline::before {
  background: radial-gradient(circle, rgba(239, 68, 68, 0.08), transparent);
}
.service-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  gap: 12px;
}
.service-name {
  font-weight: 700;
  font-size: 1.1em;
  color: var(--dark);
  letter-spacing: -0.2px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.service-desc {
  color: var(--gray);
  font-size: 0.9em;
  margin-bottom: 14px;
  line-height: 1.5;
}
.service-meta {
  display: flex;
  justify-content: space-between;
  gap: 15px;
  font-size: 0.85em;
  color: var(--gray-light);
  flex-wrap: wrap;
  font-weight: 600;
}
.service-meta span {
  display: flex;
  align-items: center;
  gap: 5px;
}
.service-uptime-windows {
  display: flex;
  gap: 15px;
  font-size: 0.78em;
  color: var(--gray-light);
  flex-wrap: wrap;
  margin-top: 6px;
}
/* Internal elements for service logs and graphs inside untouched scope */
.status-graph {
  width: 100%;
  height: 100px;
  margin-top: 12px;
  position: relative;
  background-color: #0b131a;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(16, 185, 129, 0.3);
  box-shadow: inset 0 0 15px rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
}
.status-graph::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image: 
    linear-gradient(to right, rgba(16, 185, 129, 0.08) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(16, 185, 129, 0.08) 1px, transparent 1px);
  background-size: 20px 20px;
  z-index: 1;
}
.status-graph svg { width: 100%; height: 90%; position: relative; z-index: 2; }
.heartbeat-path { stroke: var(--success-color); stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round; fill: none; filter: drop-shadow(0 0 4px var(--success-color)); animation: ecgSweep 2.5s linear infinite; stroke-dasharray: 400; stroke-dashoffset: 400; }
@keyframes ecgSweep { 0% { stroke-dashoffset: 400; opacity: 0.2; } 20% { opacity: 1; } 100% { stroke-dashoffset: 0; opacity: 1; } }
.status-graph.degraded { background-color: #1a160b; border: 1px solid rgba(245, 158, 11, 0.3); }
.status-graph.degraded::before { background-image: linear-gradient(to right, rgba(245, 158, 11, 0.08) 1px, transparent 1px), linear-gradient(to bottom, rgba(245, 158, 11, 0.08) 1px, transparent 1px); }
.degraded-path { stroke: var(--warning-color); stroke-width: 2; fill: none; filter: drop-shadow(0 0 3px var(--warning-color)); animation: degradedPulse 1.8s ease-in-out infinite alternate; }
@keyframes degradedPulse { 0% { opacity: 0.4; transform: scaleY(0.95); } 100% { opacity: 1; transform: scaleY(1.05); } }
.status-graph.offline { background-color: #1a0b0b; border: 1px solid rgba(239, 68, 68, 0.3); }
.status-graph.offline::before { background-image: linear-gradient(to right, rgba(239, 68, 68, 0.08) 1px, transparent 1px), linear-gradient(to bottom, rgba(239, 68, 68, 0.08) 1px, transparent 1px); }
.dead-line { stroke: var(--danger-color); stroke-width: 2; filter: drop-shadow(0 0 4px var(--danger-color)); animation: flatlineBlink 2s ease-in-out infinite; }
@keyframes flatlineBlink { 0%, 100% { opacity: 0.25; } 50% { opacity: 0.9; } }
.service-log { margin-top: 14px; }
.service-log summary { cursor: pointer; font-size: 0.8em; font-weight: 700; color: var(--gray); text-transform: uppercase; letter-spacing: 0.4px; outline: none; }
.service-log summary:hover { color: var(--primary-color); }
.service-log pre { margin-top: 10px; padding: 12px 14px; background: #0b131a; color: #d8f0d8; border-radius: 8px; font-family: 'SFMono-Regular', Consolas, monospace; font-size: 0.78em; line-height: 1.5; white-space: pre-wrap; word-break: break-word; max-height: 260px; overflow-y: auto; }
/* ================================================================= */
/* END PRESERVED CSS                                                 */
/* ================================================================= */

/* Incidents Section Redesign */
.incidents { margin-top: 50px; }
.incidents-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.incident-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: relative;
}

.incident-item {
  background: var(--white);
  padding: 20px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  border-left: 4px solid var(--gray);
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.incident-item.resolved { border-left-color: var(--success-color); }
.incident-item.investigating { border-left-color: var(--warning-color); }
.incident-item.identified { border-left-color: var(--danger-color); }

.incident-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 10px;
}

.incident-item h3 {
  font-size: 1.1em;
  color: var(--text-secondary);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.incident-tag {
  font-size: 0.75em;
  padding: 4px 10px;
  border-radius: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.incident-tag.resolved { background: var(--badge-op-bg); color: var(--badge-op-fg); }
.incident-tag.investigating { background: var(--badge-deg-bg); color: var(--badge-deg-fg); }
.incident-tag.identified { background: var(--badge-off-bg); color: var(--badge-off-fg); }

.incident-time {
  font-size: 0.85em;
  color: var(--gray-light);
  margin-bottom: 12px;
}

.incident-log {
  margin-top: 10px;
  padding: 12px 14px;
  background: #0b131a;
  color: #ffb3b3;
  border-radius: 8px;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 0.78em;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow-y: auto;
}

.no-incidents {
  text-align: center;
  padding: 40px;
  background: var(--white);
  border: 1px dashed var(--border-hover);
  border-radius: 8px;
  color: var(--gray);
  font-size: 0.95em;
}

/* Footer Redesign */
footer {
  margin-top: 60px;
  padding: 40px 20px;
  text-align: center;
  border-top: 1px solid var(--border-color);
  color: var(--gray);
  font-size: 0.85em;
}

.footer-links a, .powered-by a {
  color: var(--primary-color);
  text-decoration: none;
  font-weight: 600;
  margin: 0 10px;
}

.footer-links a:hover, .powered-by a:hover {
  text-decoration: underline;
  color: var(--primary-dark);
}

.powered-by {
  margin-top: 20px;
  color: var(--gray-light);
}

/* Admin UI */
.admin-badge {
  padding: 4px 10px;
  border-radius: 4px;
  background: var(--dark-secondary);
  color: var(--white);
  font-size: 0.7em;
  text-transform: uppercase;
  margin-left: 10px;
  font-weight: 600;
}
.admin-badge:not([hidden]) { display: inline-flex; }

.admin-panel { margin-top: 20px; }
.admin-toggle { color: var(--gray-light); text-decoration: none; border-bottom: 1px dashed var(--gray-light); }
.admin-form { margin-top: 15px; display: flex; justify-content: center; gap: 10px; }
.admin-form input { padding: 6px 12px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 1em; }
.admin-form button { padding: 6px 16px; background: var(--primary-color); color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }
.admin-form button#adminKeyClear { background: var(--gray); }

.refresh-error {
  margin-top: 15px;
  padding: 12px;
  background: var(--warn-bg);
  border: 1px solid var(--warn-border);
  color: var(--warn-fg);
  border-radius: 8px;
  font-size: 0.85em;
}
.refresh-error:not([hidden]) { display: block; }

/* Fully Responsive Breakdown */
@media (max-width: 768px) {
  .summary-card {
    flex-direction: column;
    align-items: flex-start;
    gap: 15px;
  }
  .summary-meta {
    align-items: flex-start;
    width: 100%;
  }
  .incidents-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}

@media (max-width: 400px) {
  .container {
    padding: 15px 10px;
  }
  header {
    padding: 25px 15px;
    margin-bottom: 25px;
  }
  header h1 {
    font-size: 1.5em;
  }
  .summary-card {
    padding: 15px;
  }
  .status-badge {
    padding: 6px 10px;
    font-size: 0.8em;
  }
  .metrics h2, .services h2, .incidents h2 {
    font-size: 1.2em;
    margin-bottom: 15px;
  }
  .chart-container {
    padding: 12px;
  }
  .incident-item {
    padding: 15px;
  }
  .incident-item h3 {
    font-size: 0.95em;
    flex-direction: column;
    align-items: flex-start;
  }
  .footer-links {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .footer-links a {
    margin: 0;
  }
}
"""

STATUS_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en"__STAYPRESENT_THEME_ATTR__>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>__STAYPRESENT_TITLE__</title>
    <meta name="color-scheme" content="__STAYPRESENT_COLOR_SCHEME__">
    <meta name="description" content="__STAYPRESENT_DESCRIPTION__">
    __STAYPRESENT_OG_TAGS_BLOCK__
    <link rel="icon" href="__STAYPRESENT_FAVICON_URL__" id="favicon">
    <link rel="stylesheet" href="__STAYPRESENT_CSS_URL__" />
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js" integrity="sha384-jb8JQMbMoBUzgWatfe6COACi2ljcDdZQ2OxczGA3bGNeWe+6DChMTBJemed7ZnvJ" crossorigin="anonymous"></script>
    __STAYPRESENT_FAVICON_SCRIPT__
  </head>
  <body>
    <div class="container">
      <header>
        <h1>__STAYPRESENT_TITLE__</h1>
        <p class="subtitle">Real-time system status and incident reports</p>
      </header>

      <div class="status-summary">
        <div class="summary-card">
          <div>
            <span class="status-label">Overall Status</span>
            <span class="status-badge operational" id="overallStatus">Checking...</span>
            <span class="admin-badge" id="adminBadge" hidden>Admin view</span>
            <p class="status-counts" id="statusCounts"></p>
          </div>
          <div class="summary-meta">
            <p class="last-updated">Last updated: <span id="lastUpdated">-</span></p>
            <button class="history-toggle" id="refreshNowBtn" type="button">Refresh now</button>
          </div>
        </div>
        <p class="refresh-error" id="refreshError" hidden>
          Couldn't reach StayPresent for the latest data - showing the last known status.
        </p>
      </div>

      <section class="metrics" id="metricsSection" hidden>
        <h2>Uptime by Service</h2>
        <div class="metrics-grid">
          <div class="chart-container">
            <h3>Uptime % (since each service started)</h3>
            <canvas id="uptimeChart"></canvas>
          </div>
        </div>
      </section>

      <section class="services">
        <h2>Service Components</h2>
        <div class="service-filters">
          <button class="filter-btn active" data-filter="all">All</button>
          <button class="filter-btn" data-filter="operational">Operational</button>
          <button class="filter-btn" data-filter="degraded">Degraded</button>
          <button class="filter-btn" data-filter="offline">Offline</button>
        </div>
        <div class="service-list" id="serviceList"></div>
      </section>

      <section class="incidents">
        <div class="incidents-header">
          <h2>Incident History</h2>
          <button class="history-toggle" id="historyToggle" hidden>Show older incidents</button>
        </div>
        <div class="incident-list" id="incidentList"></div>
      </section>

      <footer>
__STAYPRESENT_COPYRIGHT_BLOCK__
__STAYPRESENT_FOOTER_LINKS_BLOCK__
        <div class="admin-panel" id="adminPanel" hidden>
          <a href="#" class="admin-toggle" id="adminToggle">Admin</a>
          <div class="admin-form" id="adminForm" hidden>
            <label for="adminKeyInput" class="sr-only" style="display:none;">Admin key</label>
            <input type="password" id="adminKeyInput" placeholder="Admin key" autocomplete="off" />
            <button type="button" id="adminKeySubmit">Unlock</button>
            <button type="button" id="adminKeyClear" hidden>Log out</button>
            <span class="admin-msg" id="adminMsg"></span>
          </div>
        </div>
        <div class="powered-by">
          Powered by <a href="https://github.com/StayElite/StayPresent">StayPresent</a>
        </div>
      </footer>
    </div>
    <script src="__STAYPRESENT_JS_URL__"></script>
  </body>
</html>"""

STATUS_JS = """// StayPresent status page client script.
const STAYPRESENT_DATA_URL = new URL('api/status.json', window.location.href).toString();
// Default until the first successful fetch tells us this route's own
// configured value (staypresent.web.status()'s poll_seconds=) - see
// STAYPRESENT_DATA_URL's response ("poll_seconds") and setPollInterval()
// below. Kept mutable (let, not const) for exactly that reason.
let STAYPRESENT_POLL_MS = 15000;
const STAYPRESENT_ADMIN_STORAGE_KEY = 'staypresent_admin_key:' + window.location.pathname;
const STAYPRESENT_ADMIN_KEY_TTL_MS = 24 * 60 * 60 * 1000; 

let currentFilter = 'all';
const openLogTails = new Set();
let showFullHistory = false;
let latestData = {
  overall_status: 'operational', services: [], incidents: [],
  generated_at: null, admin: false, admin_available: null,
};
let uptimeChart = null;
let adminKey = '';

function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function cleanServiceName(name) {
  if (!name) return '';
  let cleanName = escapeHtml(name);
  if (cleanName.endsWith(' - Worker')) {
    return cleanName.slice(0, -9);
  } else if (cleanName.endsWith(' - Web')) {
    return cleanName.slice(0, -6);
  }
  return cleanName;
}

function getServiceTypeBadge(name) {
  if (!name) return '';
  let cleanName = escapeHtml(name);
  if (cleanName.endsWith(' - Worker')) {
    return '<span class="service-type-badge worker">Worker</span>';
  } else if (cleanName.endsWith(' - Web')) {
    return '<span class="service-type-badge web">Web</span>';
  }
  return '';
}

function loadStoredAdminKey() {
  try {
    const raw = window.localStorage.getItem(STAYPRESENT_ADMIN_STORAGE_KEY);
    if (!raw) return '';
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed.key !== 'string' || typeof parsed.savedAt !== 'number') return '';
    if (Date.now() - parsed.savedAt > STAYPRESENT_ADMIN_KEY_TTL_MS) {
      window.localStorage.removeItem(STAYPRESENT_ADMIN_STORAGE_KEY);
      return '';
    }
    return parsed.key;
  } catch (err) { return ''; }
}

function storeAdminKey(key) {
  try {
    if (key) {
      window.localStorage.setItem(STAYPRESENT_ADMIN_STORAGE_KEY, JSON.stringify({ key, savedAt: Date.now() }));
    } else {
      window.localStorage.removeItem(STAYPRESENT_ADMIN_STORAGE_KEY);
    }
  } catch (err) {}
}

adminKey = loadStoredAdminKey();

function getStatusIndicator(status) { return `<span class="status-indicator ${status}"></span>`; }

const STAYPRESENT_FAVICON_COLORS = { operational: '%2310b981', degraded: '%23f59e0b', offline: '%23ef4444', unknown: '%2394a3b8' };

function updateFavicon(status) {
  // A caller-supplied favicon (staypresent.web.status(favicon=...)) stays
  // put - it isn't overwritten by the live status dot.
  if (window.STAYPRESENT_CUSTOM_FAVICON) return;
  const color = STAYPRESENT_FAVICON_COLORS[status] || STAYPRESENT_FAVICON_COLORS.unknown;
  const svg = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='14' fill='${color}'/%3E%3C/svg%3E`;
  document.getElementById('favicon').setAttribute('href', svg);
}

function getRealisticHeartbeatPath() {
  return `M 0 20 L 30 20 L 38 17 L 44 20 L 48 20 L 53 13 L 57 2 L 63 35 L 67 20 L 76 20 L 84 10 L 92 20 L 130 20 L 160 20 L 168 17 L 174 20 L 178 20 L 183 13 L 187 2 L 193 35 L 197 20 L 206 20 L 214 10 L 222 20 L 300 20`;
}

function getDegradedWavePath() {
  return `M 0 20 Q 25 5 50 20 T 100 20 T 150 20 T 200 20 T 250 20 T 300 20`;
}

function getStatusGraph(status) {
  if (status === 'operational') return `<div class="status-graph"><svg viewBox="0 0 300 40" preserveAspectRatio="none"><path class="heartbeat-path" d="${getRealisticHeartbeatPath()}"/></svg></div>`;
  else if (status === 'degraded') return `<div class="status-graph degraded"><svg viewBox="0 0 300 40" preserveAspectRatio="none"><path class="degraded-path" d="${getDegradedWavePath()}"/></svg></div>`;
  else if (status === 'offline') return `<div class="status-graph offline"><svg viewBox="0 0 300 40" preserveAspectRatio="none"><line class="dead-line" x1="0" y1="20" x2="300" y2="20"/></svg></div>`;
  return '';
}

function titleCase(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

function updateLastUpdated() {
  const el = document.getElementById('lastUpdated');
  if (!latestData.generated_at) { el.textContent = '-'; return; }
  const d = new Date(latestData.generated_at * 1000);
  el.textContent = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'UTC' }) + ' UTC';
}

function renderLogTail(log, serviceName) {
  if (!log || log.length === 0) return '';
  const lineCount = log.length;
  const text = log.map(escapeHtml).join('\\n');
  const isOpen = openLogTails.has(serviceName);
  return `<details class="service-log" data-service="${escapeHtml(serviceName)}"${isOpen ? ' open' : ''}><summary>Last log (${lineCount} line${lineCount === 1 ? '' : 's'})</summary><pre>${text}</pre></details>`;
}

function setupLogTracking() {
  document.getElementById('serviceList').addEventListener('toggle', (event) => {
    const details = event.target;
    if (!details.classList || !details.classList.contains('service-log')) return;
    const name = details.dataset.service;
    if (!name) return;
    if (details.open) openLogTails.add(name);
    else openLogTails.delete(name);
  }, true);
}

function renderServices() {
  const serviceList = document.getElementById('serviceList');
  const services = latestData.services || [];
  const filtered = currentFilter === 'all' ? services : services.filter(s => s.status === currentFilter);

  if (filtered.length === 0) {
    serviceList.innerHTML = '<div class="no-incidents">No services to show</div>';
    return;
  }

  serviceList.innerHTML = filtered.map(service => `
    <div class="service-item ${service.status}">
      <div class="service-header">
        <span class="service-name">${getStatusIndicator(service.status)} ${cleanServiceName(service.name)}</span>
        <div class="badge-group">
          <span class="status-badge ${service.status}">${getStatusIndicator(service.status)} ${titleCase(service.status)}</span>
          ${getServiceTypeBadge(service.name)}
        </div>
      </div>
      ${service.description ? `<p class="service-desc">${escapeHtml(service.description)}</p>` : ''}
      ${getStatusGraph(service.status)}
      <div class="service-meta">
        ${service.uptime !== null && service.uptime !== undefined ? `<span>Uptime: ${service.uptime}%</span>` : ''}
        ${service.restarts !== null && service.restarts !== undefined ? `<span>Restarts: ${service.restarts}</span>` : ''}
      </div>
      ${renderUptimeWindows(service)}
      ${renderLogTail(service.log, service.name)}
    </div>
  `).join('');
}

function renderUptimeWindows(service) {
  const windows = [['24h', service.uptime_24h], ['7d', service.uptime_7d], ['30d', service.uptime_30d]].filter(([, value]) => value !== null && value !== undefined);
  if (windows.length === 0) return '';
  return `<div class="service-uptime-windows">${windows.map(([label, value]) => `<span>${label}: ${value}%</span>`).join('')}</div>`;
}

function renderIncidents() {
  const incidentList = document.getElementById('incidentList');
  const incidents = latestData.incidents || [];
  if (incidents.length === 0) {
    incidentList.innerHTML = '<div class="no-incidents">No incidents reported</div>';
    return;
  }
  incidentList.innerHTML = incidents.map(incident => `
    <div class="incident-item ${incident.status}">
      <div class="incident-header">
        <h3>${incident.service ? cleanServiceName(incident.service) + ': ' : ''}${escapeHtml(incident.title)}</h3>
        <div class="badge-group">
          <span class="incident-tag ${incident.status}">${titleCase(incident.status)}</span>
          ${incident.service ? getServiceTypeBadge(incident.service) : ''}
        </div>
      </div>
      <p class="incident-time">${escapeHtml(incident.time_display)}</p>
      ${incident.log_line ? `<pre class="incident-log">${escapeHtml(incident.log_line)}</pre>` : ''}
    </div>
  `).join('');
}

function updateOverallStatus() {
  const status = latestData.overall_status || 'operational';
  const statusBadge = document.getElementById('overallStatus');
  statusBadge.innerHTML = `${getStatusIndicator(status)}${titleCase(status)}`;
  statusBadge.className = `status-badge ${status}`;
  updateFavicon(status);
  renderStatusCounts();
}

function renderStatusCounts() {
  const el = document.getElementById('statusCounts');
  const services = (latestData.services || []).filter(s => s.uptime !== null && s.uptime !== undefined);
  if (services.length <= 1) { el.textContent = ''; return; }
  const counts = { operational: 0, degraded: 0, offline: 0 };
  services.forEach(s => { if (s.status in counts) counts[s.status] += 1; });
  const parts = [`${counts.operational} of ${services.length} operational`];
  if (counts.degraded > 0) parts.push(`${counts.degraded} degraded`);
  if (counts.offline > 0) parts.push(`${counts.offline} offline`);
  el.textContent = parts.join(' \\u00b7 ');
}

/* Modifying chart creation logic to use Line chart for styling changes */
function renderUptimeChart() {
  const services = latestData.services || [];
  const withUptime = services.filter(s => s.uptime !== null && s.uptime !== undefined);
  const section = document.getElementById('metricsSection');

  if (withUptime.length === 0) { section.hidden = true; return; }
  section.hidden = false;

  const ctx = document.getElementById('uptimeChart').getContext('2d');
  const labels = withUptime.map(s => s.name);
  const data = withUptime.map(s => s.uptime);

  if (uptimeChart) {
    uptimeChart.data.labels = labels;
    uptimeChart.data.datasets[0].data = data;
    uptimeChart.update();
    return;
  }

  // Read the page's current theme colors (see the --gray/--border-color
  // variables in status_assets.py's CSS, which already flip for dark
  // mode) instead of hardcoding light-mode-only hex values here, so the
  // chart's own axis/grid stay legible under mode="dark" too.
  const rootStyles = getComputedStyle(document.documentElement);
  const tickColor = rootStyles.getPropertyValue('--gray').trim() || '#64748b';
  const gridColor = rootStyles.getPropertyValue('--border-color').trim() || '#e2e8f0';

  uptimeChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Uptime %',
        data,
        borderColor: '#ef4444',
        backgroundColor: 'rgba(239, 68, 68, 0.15)',
        borderWidth: 3,
        pointBackgroundColor: '#dc2626',
        pointBorderColor: '#ffffff',
        pointBorderWidth: 2,
        pointRadius: 5,
        fill: true,
        tension: 0.3
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: {
          min: 0, max: 100,
          ticks: { color: tickColor, font: { family: 'Inter' } },
          grid: { color: gridColor, drawBorder: false },
        },
        x: {
          ticks: { color: tickColor, font: { family: 'Inter' } },
          grid: { display: false },
        },
      },
    },
  });
}

function setupFilters() {
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter;
      renderServices();
    });
  });
}

function updateAdminUI() {
  const panel = document.getElementById('adminPanel');
  if (!latestData.admin_available) { panel.hidden = true; return; }
  panel.hidden = false;
  const badge = document.getElementById('adminBadge');
  const clearBtn = document.getElementById('adminKeyClear');
  const submitBtn = document.getElementById('adminKeySubmit');
  const input = document.getElementById('adminKeyInput');
  const msg = document.getElementById('adminMsg');

  badge.hidden = !latestData.admin;

  if (latestData.admin) {
    clearBtn.hidden = false; submitBtn.hidden = true; input.hidden = true;
    msg.textContent = 'Admin view active.';
  } else {
    clearBtn.hidden = true; submitBtn.hidden = false; input.hidden = false;
    msg.textContent = adminKey && latestData.generated_at ? 'Incorrect key.' : '';
  }
}

function setupAdminPanel() {
  const toggle = document.getElementById('adminToggle');
  const form = document.getElementById('adminForm');
  const input = document.getElementById('adminKeyInput');
  const submitBtn = document.getElementById('adminKeySubmit');
  const clearBtn = document.getElementById('adminKeyClear');

  toggle.addEventListener('click', (e) => { e.preventDefault(); form.hidden = !form.hidden; });
  const submit = () => { adminKey = input.value.trim(); storeAdminKey(adminKey); refreshData(); };
  submitBtn.addEventListener('click', submit);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
  clearBtn.addEventListener('click', () => { adminKey = ''; input.value = ''; storeAdminKey(''); refreshData(); });
}

function updateHistoryToggle() {
  const btn = document.getElementById('historyToggle');
  const total = latestData.total_incidents || 0;
  const shown = (latestData.incidents || []).length;
  if (!showFullHistory && total <= shown) { btn.hidden = true; return; }
  btn.hidden = false;
  btn.textContent = showFullHistory ? 'Show recent only' : 'Show older incidents';
}

function setupHistoryToggle() {
  document.getElementById('historyToggle').addEventListener('click', () => { showFullHistory = !showFullHistory; refreshData(); });
}

const STAYPRESENT_FETCH_TIMEOUT_MS = 10000;
let isRefreshing = false;
let pendingRefresh = false;
let pollTimerId = null;

// (Re)starts the poll timer at the current STAYPRESENT_POLL_MS. Called
// once up front with the built-in default, then again any time
// setPollInterval() below finds the server's configured value differs
// from what we're currently using - so a poll_seconds= change takes
// effect for an already-open tab on its very next successful fetch,
// not just for a fresh page load.
function restartPollTimer() {
  if (pollTimerId !== null) clearInterval(pollTimerId);
  pollTimerId = setInterval(pollTick, STAYPRESENT_POLL_MS);
}

// Adopts this route's own poll_seconds (see staypresent.web.status())
// from the data response - carried there rather than templated into
// this file so STATUS_JS can stay one static, shared asset across every
// status page on the site (see _SHARED_STATUS_JS_PATH in server.py).
function setPollInterval(data) {
  const seconds = data && data.poll_seconds;
  if (typeof seconds !== 'number' || !(seconds > 0)) return;
  const ms = seconds * 1000;
  if (ms === STAYPRESENT_POLL_MS) return;
  STAYPRESENT_POLL_MS = ms;
  restartPollTimer();
}

async function refreshData() {
  if (isRefreshing) { pendingRefresh = true; return; }
  isRefreshing = true;
  const errorBanner = document.getElementById('refreshError');
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), STAYPRESENT_FETCH_TIMEOUT_MS);
  try {
    const headers = {};
    if (adminKey) headers['X-API-Key'] = adminKey;
    const url = showFullHistory ? `${STAYPRESENT_DATA_URL}?history=1` : STAYPRESENT_DATA_URL;
    const res = await fetch(url, { headers, signal: controller.signal });
    if (!res.ok) throw new Error(`status data request failed: ${res.status}`);
    latestData = await res.json();
  } catch (err) {
    console.error('StayPresent status page: failed to refresh data', err);
    errorBanner.hidden = false; isRefreshing = false; clearTimeout(timeoutId);
    if (pendingRefresh) { pendingRefresh = false; refreshData(); }
    return;
  }
  clearTimeout(timeoutId);
  errorBanner.hidden = true;
  setPollInterval(latestData);
  updateOverallStatus();
  updateLastUpdated();
  renderServices();
  renderIncidents();
  renderUptimeChart();
  updateAdminUI();
  updateHistoryToggle();
  isRefreshing = false;
  if (pendingRefresh) { pendingRefresh = false; refreshData(); }
}

function pollTick() { if (!document.hidden) refreshData(); }
document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshData(); });

function setupRefreshButton() { document.getElementById('refreshNowBtn').addEventListener('click', () => { refreshData(); }); }

setupFilters(); setupAdminPanel(); setupLogTracking(); setupHistoryToggle(); setupRefreshButton();
refreshData(); restartPollTimer();
"""