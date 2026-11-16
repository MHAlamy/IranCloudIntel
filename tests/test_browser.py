"""Tests for environment-configured browser launching."""

import pytest

from playwright.sync_api import sync_playwright

from collectors.browser import describe_browser_config, launch_browser, resolve_browser_options


def test_default_resolves_to_bundled_chromium(monkeypatch):
    monkeypatch.delenv("BROWSER_CHANNEL", raising=False)
    monkeypatch.delenv("BROWSER_EXECUTABLE_PATH", raising=False)
    options = resolve_browser_options()
    assert "channel" not in options and "executable_path" not in options
    assert describe_browser_config() == "bundled chromium"


def test_channel_and_executable_path_precedence(monkeypatch):
    monkeypatch.setenv("BROWSER_CHANNEL", "msedge")
    monkeypatch.setenv("BROWSER_EXECUTABLE_PATH", "")
    options = resolve_browser_options()
    assert options["channel"] == "msedge"

    monkeypatch.setenv("BROWSER_EXECUTABLE_PATH", "/usr/bin/chromium")
    options = resolve_browser_options()
    assert options["executable_path"] == "/usr/bin/chromium"


@pytest.mark.browser
def test_launch_bundled_chromium_and_render_page():
    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page()
        page.goto("data:text/html,<h1>collector-ok</h1>")
        assert "collector-ok" in page.content()
        browser.close()


@pytest.mark.browser
def test_launch_edge_channel(monkeypatch):
    monkeypatch.setenv("BROWSER_CHANNEL", "msedge")
    with sync_playwright() as p:
        browser = launch_browser(p)
        assert browser.browser_type.name == "chromium"
        page = browser.new_page()
        page.goto("data:text/html,<h1>edge-ok</h1>")
        assert "edge-ok" in page.content()
        browser.close()
