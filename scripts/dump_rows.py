"""Debug: dump every rendered row (provider, plan, price, basis) from the live page."""

import re
import sys

import httpx
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

t = httpx.get("http://127.0.0.1:8000/vm?tier=standard&size=medium").text
soup = BeautifulSoup(t, "html.parser")
for tr in soup.select("table.price-table tbody tr"):
    cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
    print(" | ".join(c[:60] for c in cells))
