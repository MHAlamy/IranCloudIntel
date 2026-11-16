"""Homepage tests: hero copy, layered product map and static methodology."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_homepage_renders_hero_and_layers(client_tuple):
    client = client_tuple[0]
    response = client.get("/")
    assert response.status_code == 200
    text = response.text
    assert "رصد بازار خدمات ابری ایران" in text
    assert "مقایسه‌ی قیمت، قابلیت‌ها و عملکرد محصولات ابری تأمین‌کنندگان ایرانی" in text
    for acronym in ("IaaS", "CaaS", "PaaS"):
        assert acronym in text
    for product in ("سرور ابری", "آبجکت استورج", "(CNAP) پلتفرم ابری توسعه اپلیکیشن",
                    "دیتابیس ابری (DBaaS)", "ابزارهای DevOps", "AIaaS", "GPUaaS"):
        assert product in text


def test_homepage_links_only_ready_products(client_tuple):
    client = client_tuple[0]
    text = client.get("/").text
    assert 'href="/vm"' in text
    assert 'href="/object-storage"' in text
    for future_route in ("/cdn", "/gpu", "/kaas", "/cnap", "/dbaas", "/devops", "/aiaas"):
        assert f'href="{future_route}"' not in text
    assert "به‌زودی" in text


def test_homepage_explains_methodology(client_tuple):
    client = client_tuple[0]
    text = client.get("/").text
    assert "این داشبورد چگونه کار می‌کند؟" in text
    assert "صفحات رسمی قیمت" in text
    assert "کاتالوگ‌های قیمت" in text
    assert "عملکرد" in text
