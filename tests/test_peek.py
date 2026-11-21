from scripts.peek import DEFAULT_MAX_BYTES, peek


def _log(tmp_path, count=1000):
    path = tmp_path / 'big.log'
    path.write_text('\n'.join(f'line {i}' for i in range(count)), encoding='utf-8')
    return path


def test_default_is_bounded_and_points_to_more(tmp_path):
    path = _log(tmp_path)
    before = path.read_bytes()
    body, footer = peek(path)
    lines = body.splitlines()
    assert len(lines) == 80
    assert lines[0] == 'line 0' and lines[-1] == 'line 79'
    assert '1000 lines' in footer
    assert 'Full file on disk' in footer
    assert path.read_bytes() == before

    body, footer = peek(path, lines=1000, max_bytes=200)
    assert len(body) <= 200
    assert 'capped at 200 bytes' in footer


def test_tail_offset_and_long_line_cap(tmp_path):
    path = _log(tmp_path)
    assert peek(path, tail=True, lines=3)[0].splitlines() == ['line 997', 'line 998', 'line 999']
    assert peek(path, offset=101, lines=2)[0].splitlines() == ['line 100', 'line 101']

    path.write_text('x' * 5000, encoding='utf-8')
    body, _ = peek(path)
    assert len(body) <= DEFAULT_MAX_BYTES
    assert 'chars]' in body


def test_max_bytes_counts_utf8_bytes_not_characters(tmp_path):
    path = tmp_path / 'persian.log'
    path.write_text('قیمت ' * 200, encoding='utf-8')
    body, footer = peek(path, max_bytes=300)
    assert len(body.encode('utf-8')) <= 300
    assert '[truncated]' in body
    assert 'capped at 300 bytes' in footer


def test_grep_match_survives_a_tight_byte_budget(tmp_path):
    path = tmp_path / 'persian.json'
    path.write_text('ق' * 300 + 'NEEDLE' + 'ق' * 300, encoding='utf-8')
    body, _ = peek(path, pattern='needle', max_bytes=200)
    assert 'NEEDLE' in body
    assert len(body.encode('utf-8')) <= 200


def test_grep_reports_matches_and_context(tmp_path):
    path = tmp_path / 'app.log'
    path.write_text('INFO ok\nERROR boom\ndetail\nINFO ok2\n', encoding='utf-8')
    body, footer = peek(path, pattern='error', context=1)
    assert body.splitlines() == ['     1  INFO ok', '     2  ERROR boom', '     3  detail']
    assert '1 of 1 matches' in footer


def test_grep_shows_a_match_beyond_the_line_clip(tmp_path):
    path = tmp_path / 'minified.json'
    path.write_text('a' * 600 + 'NEEDLE' + 'b' * 600, encoding='utf-8')
    body, footer = peek(path, pattern='needle')
    assert 'NEEDLE' in body
    assert '[+600 chars]' not in body  # not clipped from the start
    assert body.startswith('     1  [+')
    assert '1 of 1 matches' in footer


def test_pytest_mode_drops_passing_noise(tmp_path):
    path = tmp_path / 'pytest.log'
    path.write_text('\n'.join([
        'tests/test_a.py ..F',
        '=' * 30 + ' FAILURES ' + '=' * 30,
        '_' * 20 + ' test_a ' + '_' * 20,
        '    assert 1 == 2',
        '=' * 20 + ' short test summary info ' + '=' * 20,
        'FAILED tests/test_a.py::test_a - assert 1 == 2',
        '=' * 20 + ' 1 failed, 2 passed in 0.10s ' + '=' * 20,
    ]), encoding='utf-8')
    body, footer = peek(path, mode='pytest')
    assert 'assert 1 == 2' in body
    assert 'FAILED tests/test_a.py::test_a' in body
    assert '1 failed, 2 passed' in body
    assert 'test_a.py ..F' not in body
    assert 'failure lines' in footer

    long_log = tmp_path / 'long-pytest.log'
    long_log.write_text('\n'.join(
        ['=' * 30 + ' FAILURES ' + '=' * 30]
        + [f'filler {i}' for i in range(200)]
        + ['E   ValueError: boom']
        + ['=' * 20 + ' short test summary info ' + '=' * 20]
        + [f'FAILED tests/test_{i}.py::test_x - assert' for i in range(5)]
        + ['=' * 20 + ' 5 failed, 2 passed in 0.10s ' + '=' * 20]
    ), encoding='utf-8')
    body, footer = peek(long_log, mode='pytest', lines=30)
    assert 'ValueError: boom' in body
    assert '5 failed, 2 passed' in body
    assert 'failure lines omitted' in body
    assert 'capped at' not in footer

    body, footer = peek(long_log, mode='pytest', lines=30, max_bytes=300)
    assert len(body.encode('utf-8')) <= 300
    assert '5 failed, 2 passed' in body
    assert 'capped at 300 bytes' in footer


def test_html_mode_strips_markup_scripts_and_styles(tmp_path):
    path = tmp_path / 'page.html'
    path.write_text(
        '<html><head><style>.x{color:red}</style></head>'
        '<body><script>evil()</script><p>Hello <b>world</b></p></body></html>',
        encoding='utf-8')
    body, _ = peek(path, mode='html')
    assert body == 'Hello\nworld'


def test_binary_and_pdf_are_not_printed(tmp_path):
    path = tmp_path / 'page.pdf'
    path.write_bytes(b'%PDF-1.7\n' + b'\x00' * 100)
    body, footer = peek(path)
    assert 'not printed' in body and 'PDF' in body
    assert footer == ''


def test_utf16_logs_from_windows_redirection_are_read(tmp_path):
    path = tmp_path / 'pytest.log'
    path.write_bytes((
        'timeout\nFAILED tests/test_x.py::test_x\n'
        + '=' * 20 + ' 1 failed, 3 passed in 0.1s ' + '=' * 20
    ).encode('utf-16'))
    body, _ = peek(path, mode='pytest')
    assert 'FAILED tests/test_x.py::test_x' in body
    assert '1 failed, 3 passed' in body
