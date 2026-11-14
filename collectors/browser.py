"""Browser launch configuration.

The rendering browser is environment-configurable so the same code runs with:
- Playwright's bundled Chromium (default; installed via mirror where the
  official CDN is geo-blocked),
- a channel browser such as Microsoft Edge (BROWSER_CHANNEL=msedge), or
- an arbitrary binary path, e.g. distro-packaged Chromium on the Ubuntu VM
  (BROWSER_EXECUTABLE_PATH=/usr/bin/chromium).

Precedence: BROWSER_EXECUTABLE_PATH > BROWSER_CHANNEL > bundled Chromium.
"""

from __future__ import annotations

import os


class BrowserConfigError(RuntimeError):
    """Raised when the configured browser cannot be resolved."""


def resolve_browser_options() -> dict:
    """Return Playwright launch kwargs from environment configuration."""
    options: dict = {"headless": os.getenv("BROWSER_HEADLESS", "1") not in ("0", "false", "False")}
    executable_path = os.getenv("BROWSER_EXECUTABLE_PATH", "").strip()
    channel = os.getenv("BROWSER_CHANNEL", "").strip()
    if executable_path:
        options["executable_path"] = executable_path
    elif channel:
        options["channel"] = channel
    return options


def describe_browser_config() -> str:
    options = resolve_browser_options()
    if "executable_path" in options:
        return f"executable_path={options['executable_path']}"
    if "channel" in options:
        return f"channel={options['channel']}"
    return "bundled chromium"


def launch_browser(playwright):
    """Launch the configured browser, failing loudly if it is unavailable."""
    options = resolve_browser_options()
    try:
        return playwright.chromium.launch(**options)
    except Exception as exc:  # surface a clear configuration error
        raise BrowserConfigError(
            f"Could not launch browser ({describe_browser_config()}): {exc}"
        ) from exc
