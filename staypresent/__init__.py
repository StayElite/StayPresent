"""
StayPresent

A lightweight Python toolkit that keeps bots and background services
alive by running a dedicated web server alongside them - plus a
built-in, dependency-free Markdown-to-HTML renderer for status pages.

Documentation: https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.md
GitHub:        https://github.com/StayElite/StayPresent
PyPI:          https://pypi.org/project/staypresent/

Created and maintained by Ashish Sharma (Stay Elite).

Copyright (c) 2026 Ashish Sharma (Stay Elite)
Licensed under the MIT License. See the LICENSE file for details.
"""

from .runner import run, heartbeat
from .pinger import ping, cron, active_cron_handles
from . import web

__version__ = "1.6.0"
__all__ = ["run", "heartbeat", "web", "ping", "cron", "active_cron_handles", "__version__"]
