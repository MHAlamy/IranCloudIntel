import pytest

from collectors.common import FetchError
from collectors.waits import wait_until


class Page:
    def __init__(self):
        self.polls = 0

    def wait_for_timeout(self, interval):
        assert interval == 100
        self.polls += 1


def test_wait_returns_as_soon_as_observable_state_ready():
    page = Page()
    assert wait_until(page, lambda: 'quote' if page.polls == 2 else None, 'quote') == 'quote'
    assert page.polls == 2


def test_wait_timeout_is_explicit():
    with pytest.raises(FetchError, match='slider state'):
        wait_until(Page(), lambda: None, 'slider state', timeout_ms=0)


@pytest.mark.browser
def test_delayed_vm_price_is_not_read_before_resource_update():
    from playwright.sync_api import sync_playwright
    from collectors.browser import launch_browser
    from collectors.parspack_quotes import collect_quotes

    with sync_playwright() as p:
        browser = launch_browser(p)
        try:
            page = browser.new_page()
            page.set_content('''
                <input type="range" min="0" max="5" value="0">
                <input type="range" min="0" max="200" value="0">
                <input type="range" min="0" max="16" value="0">
                <div>رم</div><div>selected</div><div id="ram">2GB</div>
                <div>فضا</div><div>selected</div><div id="disk">25GB</div>
                <div>پردازنده</div><div>selected</div><div id="cpu">1 Core</div>
                <div>روزانه:</div><div id="price">100 تومان</div>
                <script>
                const sliders = [...document.querySelectorAll('input')];
                let pending;
                sliders.forEach(e => e.addEventListener('input', () => {
                    document.querySelector('#ram').textContent = [2,4,8,16,32,64][+sliders[0].value] + 'GB';
                    document.querySelector('#disk').textContent = (25 + 5*sliders[1].value) + 'GB';
                    document.querySelector('#cpu').textContent = (+sliders[2].value+1) + ' Core';
                    clearTimeout(pending);
                    pending = setTimeout(() => document.querySelector('#price').textContent = '500 تومان', 300);
                }));
                </script>
            ''')
            quotes = collect_quotes(page, [dict(label='medium', ram=8, disk=80, cpu=4)])
            assert quotes[0]['daily_toman'] == '500'
            assert quotes[0]['cpu'] == 4
        finally:
            browser.close()


@pytest.mark.browser
def test_storage_slider_waits_for_new_capacity_and_price():
    from playwright.sync_api import sync_playwright
    from collectors.browser import launch_browser
    from collectors.parspack_os import collect_storage_quotes

    with sync_playwright() as p:
        browser = launch_browser(p)
        try:
            page = browser.new_page()
            page.set_content('''
                <input type="radio" name="disk" value="hdd">
                <input type="radio" name="location" value="iran">
                <input type="radio" name="period" value="monthly">
                <input type="range" min="0" max="2" value="0" disabled>
                <div id="capacity">100 GB</div><div>ماهیانه</div><div id="price">200</div>
                <script>
                const slider = document.querySelector('input[type=range]');
                document.querySelectorAll('input[type=radio]').forEach(e => e.addEventListener('change', () => {
                    slider.disabled = document.querySelectorAll('input[type=radio]:checked').length !== 3;
                }));
                slider.addEventListener('input', () => {
                    const value = +slider.value;
                    setTimeout(() => {
                        document.querySelector('#capacity').textContent = (100*(value+1)) + ' GB';
                        document.querySelector('#price').textContent = String(200*(value+1));
                    }, 250);
                });
                </script>
            ''')
            quotes = collect_storage_quotes(page)
            assert [q['storage_gb'] for q in quotes] == [100, 200, 300]
            assert [q['monthly_toman'] for q in quotes] == ['200', '400', '600']
        finally:
            browser.close()
