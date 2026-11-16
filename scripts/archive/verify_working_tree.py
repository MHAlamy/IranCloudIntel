"""Verify the harness-managed dashboard instance serves the current working tree."""

import sys

import httpx
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

t = httpx.get("http://127.0.0.1:8000/vm?tier=economy&size=medium").text
soup = BeautifulSoup(t, "html.parser")

print("health:", httpx.get("http://127.0.0.1:8000/health").json())

# economy remap: Liara + ParsPack should appear on ECONOMY views now
providers = [td.get_text(strip=True) for td in soup.select("td[data-label='تأمین‌کننده']")]
print("economy/medium providers:", providers)

# chart feature present?
print("chart element present:", soup.select_one("[class*=chart]") is not None or "chart" in t.lower())

# standard view: Liara/ParsPack should be absent (they are economy now)
standard = httpx.get("http://127.0.0.1:8000/vm?tier=standard&size=medium").text
print("standard/medium Liara absent:", "Liara" not in standard)
print("standard/medium ParsPack absent:", "ParsPack" not in standard)
