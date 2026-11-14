"""Milestone 1 smoke test: verify the native Windows environment and core dependencies."""

import sys


def test_python_version():
    # Project targets Python 3.14 (installed natively on Windows).
    assert sys.version_info[:2] == (3, 14)


def test_core_dependencies_import():
    import bs4
    import fastapi
    import httpx
    import jinja2
    import pydantic
    import uvicorn

    assert httpx.__version__
    assert pydantic.__version__
    assert bs4.__version__
    assert fastapi.__version__
    assert jinja2.__version__
    assert uvicorn.__version__


def test_pydantic_model_works():
    from pydantic import BaseModel

    class PriceObservation(BaseModel):
        provider: str
        service: str
        original_price: int
        currency: str

    obs = PriceObservation(
        provider="ArvanCloud",
        service="vm",
        original_price=1_401_480,
        currency="Toman",
    )
    assert obs.original_price == 1_401_480


def test_beautifulsoup_parses_html():
    from bs4 import BeautifulSoup

    html = "<table><tr><td>eco-small4</td><td>1,401,480</td></tr></table>"
    soup = BeautifulSoup(html, "html.parser")
    row = soup.find("table").find_all("td")
    assert row[0].text == "eco-small4"
    assert row[1].text == "1,401,480"
