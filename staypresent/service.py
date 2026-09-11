"""
StayPresent - Boot-Level Restart (systemd)

staypresent.restart() installs a user-level systemd unit so your script
comes back automatically after a full OS reboot - the one thing
staypresent.run()'s own in-process restart logic can never do by
itself, since a reboot kills the Python process (and everything it was
watching) outright. Modeled after Docker's `--restart` flag, but scoped
to what a plain user-level systemd unit can actually promise (see this
module's own docstrings below for exactly where that overlaps with
Docker's semantics and where it doesn't).

Part of the StayPresent project.
Docs: https://github.com/StayElite/StayPresent/blob/main/DOCUMENTATION.md
"""

# Created and maintained by Ashish Sharma (Stay Elite).
# Copyright (c) 2026 Ashish Sharma (Stay Elite)
# Licensed under the MIT License. See the LICENSE file for details.

import getpass
import logging
import os
import platform
import re
import shutil
import subprocess
import sys

logger = logging.getLogger("staypresent")

_VALID_POLICIES = {"no", "on-failure", "always", "unless-stopped"}
# A systemd unit name may contain letters, digits, ':', '-', '_', '.', '\' -
# kept far narrower here (alnum/-/_ only) since this is auto-derived from a
# script filename that could contain almost anything.
_UNIT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _default_service_name() -> str:
    """
    Derives a systemd-safe unit name from the running script's own
    filename - e.g. "bot.py" -> "staypresent-bot". Prefixed with
    "staypresent-" so it's obviously ours in `systemctl --user list-units`
    output, alongside every other unit on the system.
    """
    stem = os.path.splitext(os.path.basename(sys.argv[0] or "bot"))[0]
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", stem).strip("-") or "bot"
    return f"staypresent-{safe}"


_SYSTEMD_SPECIAL_RE = re.compile(r'[\s"\'\\$]')


def _systemd_quote(arg: str) -> str:
    """
    Quote a single `ExecStart=` argument per systemd's own command-line
    grammar (see systemd.service(5)/systemd.syntax(7)) - NOT POSIX shell
    syntax. systemd parses `ExecStart=` itself; the line is never handed
    to `/bin/sh`, so a POSIX-shell quoting helper like `shlex.quote()`
    (which this used to use) can produce output that systemd's own
    similar-but-not-identical grammar doesn't parse the way intended -
    most notably for an argument containing a literal single quote,
    where `shlex.quote()`'s close-quote/reopen-quote trick relies on a
    real shell's word-concatenation behavior that systemd's parser isn't
    documented to replicate. Always wraps in double quotes (never single
    - single quotes aren't special to systemd's own grammar at all) and
    escapes only what's documented as special inside a double-quoted
    systemd argument: `\\`, `"`, and `$` (as `$$`, so it isn't mistaken
    for a variable expansion).
    """
    if arg and not _SYSTEMD_SPECIAL_RE.search(arg):
        return arg
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("$", "$$")
    return f'"{escaped}"'


def restart(
    policy: str = "no",
    name: str = None,
    command: list = None,
    working_directory: str = None,
    restart_sec: float = 3,
    enable_linger: bool = True,
) -> dict:
    """
    Install (and enable) a user-level systemd unit so this script is
    automatically relaunched by systemd - both after a crash and, more
    importantly, after the whole machine reboots. This is the one thing
    `staypresent.run()`'s own restart logic can't do on its own: it only
    ever runs *inside* a live Python process, and a reboot (or a `kill
    -9` on the process itself, or the machine losing power) takes that
    process down with nothing left running to restart anything.

    This deliberately mirrors Docker's own `--restart` flag (see
    https://docs.docker.com/engine/containers/start-containers-automatically/)
    - the same four values, meaning close to the same thing - but it is
    NOT a drop-in equivalent; see "How this differs from Docker" below
    before relying on it for anything Docker-exact. Defaults to "no",
    same as Docker: calling this with no arguments at all does nothing
    (see `policy` below) - you have to opt in to a real policy.

    Meant to be called once, from the same script that calls
    `staypresent.run()` - typically right before it:

        staypresent.restart(policy="always")
        staypresent.run("bot.py")

    Running this line does NOT restart or relaunch anything immediately
    - it only writes the unit file and enables it (`systemctl --user
    enable`), so systemd will start it the *next* time this user logs in
    (or, with `enable_linger=True`, the next time the machine boots at
    all - see `enable_linger` below). It deliberately never calls
    `systemctl --user start` itself: if it did, running this same script
    a second time (e.g. to just re-check its own config, or as part of a
    restart already triggered by systemd) would launch a second,
    independent copy of your bot alongside the one already running this
    very line - silently duplicating it instead of managing it. Start it
    under systemd yourself, once, with (as printed at the end):

        systemctl --user start <name>

    (stopping any copy you started by hand first, so you don't end up
    with two).

    Args:
        policy: Restart policy, matching Docker's own four values:
            - "no" (the default): does nothing at all - no unit is
              written, `systemctl`/`loginctl` are never invoked, and
              every other argument to this call is ignored. This is
              deliberate, not a stub: it's what makes it safe to leave
              `staypresent.restart()` in a script unconditionally
              (nothing to configure, nothing to remove later) and it's
              also why this never requires Linux/systemd at all - see
              below.
            - "always": restart no matter how the process exits,
              including a clean/manual stop.
            - "on-failure" (optionally "on-failure:N"): only restart on
              a crash - not on a clean exit, and not automatically after
              this unit is otherwise stopped. ":N" gives up after N
              restarts within a rolling window - see "How this differs
              from Docker" below for exactly what that window means
              here.
            - "unless-stopped": restart like "always", with one
              intended difference - a manual stop should "stick" across
              a later reboot. There's no real systemd primitive for
              that (see "How this differs from Docker" below) - this is
              implemented as plain `Restart=always` under the hood, and
              a `logger.warning()` is emitted every time this policy is
              used, spelling out exactly where it falls short of real
              Docker behavior. Prefer "always" instead unless you
              specifically want the closest available approximation and
              have read that warning.
            Only Linux/systemd requirements below apply to "always",
            "on-failure", and "unless-stopped" - never to "no".
        name: Systemd unit name (without ".service"). Defaults to
            "staypresent-<script filename>" (e.g. "staypresent-bot" for
            "bot.py"). Must contain only letters, digits, "-", "_" if
            given explicitly - pick your own if the auto-derived default
            collides with something, e.g. when installing this for two
            different scripts that happen to share a filename. Ignored
            when `policy="no"`.
        command: The exact command to (re)launch, as a list of argv
            strings (e.g. `["python3", "/home/alice/bot/bot.py"]`).
            Defaults to the currently running interpreter and script -
            `[sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:]`
            - which is right for the common case of calling this from
            the top of the same script `staypresent.run()` is called
            from. Give this explicitly if you're installing the unit
            from a separate one-off setup script rather than the bot
            script itself, or if `sys.argv[0]` is empty in your context
            (e.g. a `python3 -c ...` one-liner or certain embedders) -
            there's nothing to auto-derive a path from there, so this is
            required in that case (raises `ValueError` otherwise).
            Ignored when `policy="no"`.
        working_directory: Directory the command runs from. Defaults to
            the current working directory at the moment this is called
            - matters if your bot reads/writes relative paths. Ignored
            when `policy="no"`.
        restart_sec: Seconds systemd waits before each restart attempt.
            Defaults to 3. A very low value (e.g. 0) can spin
            aggressively if the process fails instantly every time;
            systemd's own `StartLimitBurst`/`StartLimitIntervalSec` (set
            from `policy`'s `:N`, or a sane built-in default otherwise)
            is the real backstop against that either way. Ignored when
            `policy="no"`.
        enable_linger: Whether to also attempt `loginctl enable-linger`
            for the current user. Without this, a `systemctl --user`
            unit only starts once that user has an active login
            session - fine on a desktop you log into, but on a
            headless server it means the unit won't actually come back
            after a reboot until someone logs in as this user again,
            which defeats the point. This is attempted best-effort: some
            systems restrict who can enable their own lingering, so a
            failure here is logged as a warning (with the exact command
            to try yourself) rather than raised, since the unit itself
            is still correctly installed and enabled either way. Ignored
            when `policy="no"`.

    Returns:
        A dict describing what was done: `{"name", "unit_path", "command",
        "policy", "linger_enabled", "start_command", "installed"}` -
        `start_command` is the exact `systemctl --user start ...` line
        to run yourself when you're ready to hand off to systemd (see
        above for why this function never runs it for you). For
        `policy="no"`, `"installed"` is `False` and every other key
        besides `"policy"` is `None`.

    Raises:
        RuntimeError: for "always"/"on-failure"/"unless-stopped" only -
            if not running on Linux, if `systemctl` isn't available on
            this system, or if `systemctl --user enable` itself fails
            (e.g. no user systemd instance/D-Bus session available at
            all - common in some minimal containers). Never raised for
            `policy="no"`, regardless of platform.
        TypeError: if `policy`/`name`/`working_directory` isn't a str
            (or None where allowed), or if `command` isn't a list of
            str.
        ValueError: if `policy` isn't "no", "always", "unless-stopped",
            or "on-failure" (optionally "on-failure:<positive int>" -
            including "always:N"/"no:N"/"unless-stopped:N", which Docker
            itself also rejects - the retry limit only applies to
            "on-failure"), if `name` contains anything other than
            letters/digits/"-"/"_", if `command` is an empty list, if
            `restart_sec` is negative, or if `command` wasn't given and
            `sys.argv[0]` is empty (nothing to auto-derive a command
            from - give `command` explicitly instead).

    How this differs from Docker:
        - Docker's daemon (and so every container's restart policy) is
          managed by one long-lived, always-installed system service
          (`dockerd`, itself a systemd unit) that's guaranteed to exist
          the moment the machine finishes booting. `staypresent.restart()`
          instead creates one new, ordinary `systemctl --user` unit per
          script - there's no separate "StayPresent daemon" coordinating
          anything; systemd itself is the entire mechanism.
        - Docker's `on-failure[:max-retries]` counts total restart
          attempts, forever, no matter how far apart they are. Systemd
          has no equivalent "N attempts, ever" counter - the closest
          available primitive is `StartLimitBurst`/`StartLimitIntervalSec`,
          a rolling-window rate limiter: at most N restarts within a
          given time window (this function uses N (or 5, if no `:N` was
          given) restarts per 5-minute window) before systemd stops
          trying *for that window* and marks the unit failed. A process
          that crashes once every 10 minutes, for instance, would keep
          being restarted forever under this scheme, since it never hits
          N failures within any single window - unlike Docker's literal
          lifetime cap. Close enough to guard against a genuine crash
          loop, but not the same guarantee.
        - Docker's `unless-stopped` (restart always, except a manual
          stop persists across a daemon/machine restart) has no clean
          systemd equivalent, because a `systemctl --user stop` doesn't
          durably record "the human wanted this off" anywhere a later
          boot would consult - it's just not currently running, and an
          *enabled* unit starts again on the next boot/login regardless.
          `policy="unless-stopped"` is implemented as plain
          `Restart=always` for this reason - concretely, stop this
          service by hand and then reboot, and systemd WILL start it
          again (unlike real Docker `unless-stopped`), unless you also
          run `systemctl --user disable <name>.service` for a stop that
          actually sticks.
        - Docker's `no` (the default for both Docker and this function)
          means a container is never automatically restarted for any
          reason, by any mechanism - closest available comparison here
          is simply never calling this function at all, which is
          exactly what `policy="no"` does: nothing.
        - `enable_linger` aside, Docker containers are restarted by a
          system-wide daemon regardless of whether anyone is logged in.
          A `systemctl --user` unit fundamentally depends on that user's
          systemd instance existing, which needs either an active login
          session or lingering enabled for that user - there's no
          "always-on regardless of login" mode for a *user*-level unit
          short of lingering.
    """
    if not isinstance(policy, str) or not policy.strip():
        raise TypeError(f"staypresent.restart(): 'policy' must be a non-empty str, got {policy!r}.")
    policy_raw = policy.strip()
    policy_name, _, retries_part = policy_raw.partition(":")
    if policy_name not in _VALID_POLICIES:
        raise ValueError(
            f"staypresent.restart(): policy={policy!r} is not recognized - use \"no\" (the "
            "default), \"always\", \"on-failure\" (optionally \"on-failure:N\"), or "
            "\"unless-stopped\" - the same four values as Docker's own --restart flag."
        )
    max_retries = None
    if retries_part:
        if policy_name != "on-failure":
            raise ValueError(
                f"staypresent.restart(): policy={policy!r} - a ':N' retry limit is only valid "
                "with \"on-failure\" (same as Docker's own --restart flag)."
            )
        if not retries_part.isdigit() or int(retries_part) <= 0:
            raise ValueError(
                f"staypresent.restart(): policy={policy!r} - the number after ':' must be a "
                "positive integer."
            )
        max_retries = int(retries_part)

    if policy_name == "no":
        # Deliberately does nothing at all - not even a platform check -
        # so `staypresent.restart()` (this policy is the default) is
        # always safe to leave in a script unconditionally, on any OS.
        # See this function's own docstring for why.
        logger.info(
            "staypresent.restart(): policy='no' - nothing installed (this matches Docker's own "
            "default of not automatically restarting). Pass policy=\"always\", "
            "\"on-failure\"[:N], or \"unless-stopped\" to actually set up boot-level restart via "
            "systemd."
        )
        return {
            "name": None,
            "unit_path": None,
            "command": None,
            "policy": "no",
            "linger_enabled": None,
            "start_command": None,
            "installed": False,
        }

    if platform.system() != "Linux":
        raise RuntimeError(
            f"staypresent.restart(): policy={policy!r} is only supported on Linux (systemd) "
            f"right now - detected {platform.system()!r}. There's no equivalent on this "
            "platform yet (policy=\"no\" - the default - works everywhere, since it's a no-op)."
        )
    if shutil.which("systemctl") is None:
        raise RuntimeError(
            "staypresent.restart(): 'systemctl' isn't available on this system - "
            "this requires a systemd-based Linux distribution."
        )

    if name is None:
        name = _default_service_name()
    elif not isinstance(name, str) or not name.strip():
        raise TypeError(f"staypresent.restart(): 'name' must be a non-empty str or None, got {name!r}.")
    elif not _UNIT_NAME_RE.match(name):
        raise ValueError(
            f"staypresent.restart(): name={name!r} is invalid - only letters, digits, '-', and "
            "'_' are allowed in a systemd unit name here."
        )

    if command is None:
        if not sys.argv[0]:
            raise ValueError(
                "staypresent.restart(): 'command' wasn't given, and sys.argv[0] is empty (can "
                "happen when running via `python3 -c ...`, certain embedders, or a REPL) - "
                "there's no script path to auto-derive a command from. Pass 'command' "
                "explicitly, e.g. command=[\"python3\", \"/path/to/bot.py\"]."
            )
        command = [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:]
    if not isinstance(command, list) or not command or not all(isinstance(c, str) for c in command):
        raise TypeError(
            "staypresent.restart(): 'command' must be a non-empty list of str (an argv list), "
            f"got {command!r}."
        )

    if working_directory is None:
        working_directory = os.getcwd()
    elif not isinstance(working_directory, str) or not working_directory.strip():
        raise TypeError(
            "staypresent.restart(): 'working_directory' must be a non-empty str or None, got "
            f"{working_directory!r}."
        )

    if not isinstance(restart_sec, (int, float)) or isinstance(restart_sec, bool) or restart_sec < 0:
        raise TypeError(
            f"staypresent.restart(): 'restart_sec' must be a non-negative int/float, got {restart_sec!r}."
        )

    if policy_name == "unless-stopped":
        logger.warning(
            "staypresent.restart(): policy='unless-stopped' has no exact systemd equivalent - "
            "under the hood this uses Restart=always (systemd has no primitive for \"restart "
            "unless manually stopped\", since a plain 'systemctl --user stop' doesn't persist "
            "across a reboot the way Docker's own stop does). Concretely: if you stop '%s' by "
            "hand and then reboot, systemd WILL start it again (unlike Docker's unless-stopped) "
            "- run this instead for a stop that actually sticks: systemctl --user disable %s.service",
            name, name,
        )
    # systemd's Restart= only accepts a fixed set of values (no /
    # on-success / on-failure / on-abnormal / on-watchdog / on-abort /
    # always) - "unless-stopped" isn't one of them, so it maps to
    # "always" here (see the warning above and this function's own
    # "How this differs from Docker" docstring section for exactly why).
    systemd_restart_value = "always" if policy_name == "unless-stopped" else policy_name

    exec_start = " ".join(_systemd_quote(part) for part in command)
    burst = max_retries if max_retries is not None else 5

    unit_content = (
        "[Unit]\n"
        f"Description=StayPresent-managed service ({name})\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={working_directory}\n"
        f"ExecStart={exec_start}\n"
        f"Restart={systemd_restart_value}\n"
        # Explicit "s" suffix (rather than a bare number) so a fractional
        # restart_sec (e.g. 0.5) is unambiguously parsed as 0.5 seconds -
        # systemd's own unit-less-number fallback is documented for
        # whole seconds, not guaranteed for fractional ones.
        f"RestartSec={restart_sec}s\n"
        # A rolling-window rate limiter, NOT the same as Docker's lifetime
        # max-retries counter - see this function's own docstring
        # ("How this differs from Docker") for exactly why.
        "StartLimitIntervalSec=300\n"
        f"StartLimitBurst={burst}\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )

    unit_dir = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(unit_dir, exist_ok=True)
    unit_path = os.path.join(unit_dir, f"{name}.service")
    with open(unit_path, "w", encoding="utf-8") as f:
        f.write(unit_content)

    def _run_systemctl(*args):
        return subprocess.run(
            ["systemctl", "--user", *args], capture_output=True, text=True, check=False,
        )

    reload_result = _run_systemctl("daemon-reload")
    if reload_result.returncode != 0:
        raise RuntimeError(
            "staypresent.restart(): 'systemctl --user daemon-reload' failed - is a user systemd "
            f"instance/D-Bus session available? ({reload_result.stderr.strip()})"
        )

    enable_result = _run_systemctl("enable", f"{name}.service")
    if enable_result.returncode != 0:
        raise RuntimeError(
            f"staypresent.restart(): 'systemctl --user enable {name}.service' failed - "
            f"({enable_result.stderr.strip()})"
        )

    linger_enabled = False
    if enable_linger:
        # Best-effort, like the loginctl call itself below: the unit is
        # already correctly installed and enabled at this point (the
        # daemon-reload/enable calls above already succeeded), so any
        # unexpected failure here (e.g. getpass.getuser() can raise
        # OSError on a minimal system with no user database entry) is
        # logged and swallowed rather than left to crash this call after
        # its real job is already done.
        try:
            user = getpass.getuser()
            linger_result = subprocess.run(
                ["loginctl", "enable-linger", user], capture_output=True, text=True, check=False,
            )
            linger_enabled = linger_result.returncode == 0
            if not linger_enabled:
                logger.warning(
                    "staypresent.restart(): couldn't enable lingering for '%s' (%s) - without "
                    "it, this unit only starts once you have an active login session, not on "
                    "every boot regardless of login. Try running this yourself: "
                    "loginctl enable-linger %s",
                    user, linger_result.stderr.strip(), user,
                )
        except OSError as e:
            logger.warning(
                "staypresent.restart(): couldn't attempt to enable lingering (%s) - the unit "
                "itself is still correctly installed and enabled; without lingering, it only "
                "starts once you have an active login session, not on every boot regardless of "
                "login. Try running this yourself: loginctl enable-linger <your-username>",
                e,
            )

    start_command = f"systemctl --user start {name}.service"
    if linger_enabled:
        when = "on every boot from now on (lingering is enabled for this user)"
    else:
        when = "the next time this user logs in"
    logger.info(
        "staypresent.restart(): installed and enabled '%s' at %s (policy=%s). It will start "
        "automatically %s - it was NOT started just now (see this function's own docstring "
        "for why). Run this yourself when you're ready to hand off to systemd: %s",
        name, unit_path, policy_raw, when, start_command,
    )

    return {
        "name": name,
        "unit_path": unit_path,
        "command": command,
        "policy": policy_raw,
        "linger_enabled": linger_enabled,
        "start_command": start_command,
        "installed": True,
    }
