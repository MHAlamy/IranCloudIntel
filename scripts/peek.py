"""Bounded, read-only file excerpts for agents. Full files stay untouched on disk.

Examples:
    python -m scripts.peek evidence/arvan/vm/<run>/rendered.html --html
    python -m scripts.peek logs/pytest.log --pytest
    python -m scripts.peek data/export.json --grep rate --context 2
    python -m scripts.peek huge.csv --offset 1000 --lines 20
"""
import argparse
import re
import sys
from pathlib import Path

DEFAULT_LINES = 80
DEFAULT_MAX_BYTES = 16000
MAX_LINE_CHARS = 400
PYTEST_TAIL = 20
BINARY_PREFIXES = (b'%PDF', b'PK\x03\x04', b'\x89PNG', b'GIF8')
_SEPARATOR = re.compile(r'^[=_]{3,} .* [=_]{3,}$')
_FAILED_LINE = re.compile(r'^(FAILED|ERROR) ')
_SUMMARY = re.compile(r'^\s*(?:=+\s*)?.*\b\d+ (?:passed|failed|error)\b')
_TRUNCATED = ' ... [truncated]'


def _size(n: int) -> str:
    if n < 1024:
        return f'{n} B'
    if n < 1024 ** 2:
        return f'{n / 1024:.1f} KB'
    return f'{n / 1024 ** 2:.1f} MB'


def _clip(line: str) -> str:
    # Minified JSON/HTML is one huge line; clip it so --lines alone cannot blow up.
    if len(line) <= MAX_LINE_CHARS:
        return line
    return line[:MAX_LINE_CHARS] + f' ... [+{len(line) - MAX_LINE_CHARS} chars]'


def _clip_at(line: str, start: int) -> str:
    """Clip a long line around a match, so --grep never hides what it found."""
    if len(line) <= MAX_LINE_CHARS:
        return line
    # Keep the lead-in short so even a tiny --max-bytes still shows the match.
    left = max(0, start - 30)
    right = min(len(line), left + MAX_LINE_CHARS)
    prefix = f'[+{left} chars] ' if left else ''
    suffix = f' ... [+{len(line) - right} chars]' if right < len(line) else ''
    return prefix + line[left:right] + suffix


def _read_text(path: Path) -> str | None:
    with path.open('rb') as handle:
        head = handle.read(4096)
    # Windows PowerShell 5.1 redirection writes UTF-16LE; accept it instead of
    # calling the log binary.
    if head.startswith((b'\xff\xfe', b'\xfe\xff')):
        return path.read_text(encoding='utf-16', errors='replace')
    if head.startswith(BINARY_PREFIXES) or b'\x00' in head:
        return None
    return path.read_text(encoding='utf-8-sig', errors='replace')


def _html_text(text: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text, 'html.parser')
    for tag in soup(['script', 'style']):
        tag.decompose()
    return soup.get_text('\n')


def _pytest_split(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split a pytest log into failure detail and summary/count lines."""
    failure, summary = [], []
    in_failure = False
    for line in lines:
        stripped = line.strip()
        if '=' in stripped and _SEPARATOR.match(stripped):
            if 'FAILURES' in stripped or 'ERRORS' in stripped:
                in_failure = True
                failure.append(line)
                continue
            in_failure = False
        if in_failure:
            failure.append(line)
        elif _FAILED_LINE.match(line) or _SUMMARY.match(stripped):
            summary.append(line)
    return failure, summary


def _bounded(lines: list[str], max_bytes: int) -> tuple[str, bool]:
    """Join lines without exceeding max_bytes of UTF-8 output."""
    parts, used, capped = [], 0, False
    for line in lines:
        raw = line.encode('utf-8')
        sep = 1 if parts else 0
        if used + sep + len(raw) <= max_bytes:
            parts.append(line)
            used += sep + len(raw)
            continue
        room = max_bytes - used - sep
        if room > len(_TRUNCATED):
            parts.append(raw[:room - len(_TRUNCATED)].decode('utf-8', 'ignore') + _TRUNCATED)
        capped = True
        break
    return '\n'.join(parts), capped


def _tail_bounded(lines: list[str], max_bytes: int) -> str:
    """Keep the newest lines (counts/summaries) when the budget is very small."""
    parts, used = [], 0
    for line in reversed(lines):
        raw = line.encode('utf-8')
        sep = 1 if parts else 0
        if used + sep + len(raw) <= max_bytes:
            parts.append(line)
            used += sep + len(raw)
            continue
        room = max_bytes - used - sep
        if room > len(_TRUNCATED):
            parts.append(raw[:room - len(_TRUNCATED)].decode('utf-8', 'ignore') + _TRUNCATED)
        break
    return '\n'.join(reversed(parts))


def peek(path, *, mode: str = 'text', lines: int = DEFAULT_LINES, offset: int = 0,
         tail: bool = False, pattern: str | None = None, context: int = 0,
         max_bytes: int = DEFAULT_MAX_BYTES) -> tuple[str, str]:
    """Return (body, footer) for a bounded view of ``path``."""
    path = Path(path)
    size = path.stat().st_size
    text = _read_text(path)
    if text is None:
        return (f'[peek] {path.name}: binary/PDF content ({_size(size)}) not printed; '
                'extract text with the relevant collector instead.', '')

    if mode == 'html':
        all_lines = [line.strip() for line in _html_text(text).splitlines() if line.strip()]
    else:
        all_lines = text.splitlines()

    protected: list[str] = []
    if mode == 'pytest':
        failure, summary = _pytest_split(all_lines)
        if len(failure) > lines:
            tail_n = min(PYTEST_TAIL, lines)
            head_n = lines - tail_n
            head, tail_lines = failure[:head_n], failure[-tail_n:]
            omitted = len(failure) - head_n - tail_n
            out = [_clip(line) for line in head]
            out.append(f'... [peek] {omitted} failure lines omitted ...')
        else:
            head, tail_lines, omitted = failure, [], 0
            out = [_clip(line) for line in head]
        failed = [line for line in summary if _FAILED_LINE.match(line)]
        counts = [line for line in summary if not _FAILED_LINE.match(line)]
        if len(failed) > lines:
            extra = len(failed) - lines
            failed = failed[:lines] + [f'... [peek] {extra} FAILED lines omitted ...']
        # The exception tail, FAILED list and final counts must survive the budget.
        protected = [_clip(line) for line in tail_lines + failed + counts]
        detail = f'{len(head) + len(tail_lines)} of {len(failure)} failure lines'
        if omitted:
            detail += f' ({omitted} omitted)'
        detail += f', {len(summary)} summary lines'
    elif pattern:
        rx = re.compile(pattern, re.IGNORECASE)
        hits = [i for i, line in enumerate(all_lines) if rx.search(line)]
        window = set()
        for hit in hits[:lines]:
            window.update(range(max(0, hit - context), min(len(all_lines), hit + context + 1)))
        out = []
        for i in sorted(window):
            match = rx.search(all_lines[i])
            piece = _clip_at(all_lines[i], match.start()) if match else _clip(all_lines[i])
            out.append(f'{i + 1:>6}  {piece}')
        if not out:
            out = ['(no matches)']
        detail = f'showing {len(out)} lines around {min(len(hits), lines)} of {len(hits)} matches'
    else:
        start = max(0, len(all_lines) - lines) if tail else max(0, offset - 1)
        chosen = all_lines[start:start + lines]
        out = [_clip(line) for line in chosen]
        detail = (f'last {len(out)} of {len(all_lines)} lines' if tail
                  else f'lines {start + 1}-{start + len(out)} of {len(all_lines)}'
                  if chosen else f'no lines from offset {start + 1}')

    if protected:
        reserved = '\n'.join(protected)
        reserved_bytes = len(reserved.encode('utf-8'))
        if reserved_bytes + 1 >= max_bytes:
            body, capped = _tail_bounded(protected, max_bytes), True
        else:
            head_text, capped = _bounded(out, max_bytes - reserved_bytes - 1)
            body = f'{head_text}\n{reserved}' if head_text else reserved
    else:
        body, capped = _bounded(out, max_bytes)
    if capped:
        detail += f', capped at {max_bytes} bytes'

    footer = (f'[peek] {path.name}: {len(all_lines)} lines, {_size(size)}; {detail}. '
              'More: --offset N --lines N, --tail, --grep PATTERN [--context N], '
              '--max-bytes N. Full file on disk.')
    return body, footer


def main(argv=None):
    # Evidence text is often Persian; never crash on a legacy Windows code page.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('path', type=Path)
    parser.add_argument('--lines', type=int, default=DEFAULT_LINES,
                        help=f'lines to show, or max grep matches (default {DEFAULT_LINES})')
    parser.add_argument('--offset', type=int, default=0, metavar='N',
                        help='1-based first line')
    parser.add_argument('--tail', action='store_true', help='show the last lines')
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument('--grep', metavar='PATTERN', help='case-insensitive regex filter')
    choice.add_argument('--pytest', action='store_true',
                        help='keep failure/traceback lines and the final counts')
    parser.add_argument('--html', action='store_true', help='extract visible text first')
    parser.add_argument('--context', type=int, default=0, help='context lines around grep hits')
    parser.add_argument('--max-bytes', type=int, default=DEFAULT_MAX_BYTES,
                        help=f'excerpt budget in UTF-8 bytes (default {DEFAULT_MAX_BYTES})')
    args = parser.parse_args(argv)
    if args.lines < 1 or args.offset < 0 or args.context < 0 or args.max_bytes < 200:
        parser.error('--lines >= 1, --offset/--context >= 0, --max-bytes >= 200')
    if args.tail and (args.grep or args.pytest):
        parser.error('--tail cannot be combined with --grep/--pytest')
    mode = 'pytest' if args.pytest else 'html' if args.html else 'text'
    try:
        body, footer = peek(args.path, mode=mode, lines=args.lines, offset=args.offset,
                            tail=args.tail, pattern=args.grep, context=args.context,
                            max_bytes=args.max_bytes)
    except (OSError, re.error) as exc:
        parser.exit(1, f'peek failed: {exc}\n')
    if body:
        print(body)
    if footer:
        print(footer)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
