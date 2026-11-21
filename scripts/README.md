# Inspection tools

Use `python -m scripts.inspect_data [summary|providers|runs|verification]`.
Optional `--db PATH --limit N` (default 20, maximum 1000). This command opens
SQLite read-only, does not migrate, and does not call providers or an LLM.

`db_report.py`, `check_db_providers.py` and `check_verification.py` are compatibility
wrappers for that command. Prefer module invocation from the repository root.

## Bounded output

`python -m scripts.peek PATH` prints a bounded excerpt and leaves the full file on
disk: 80 lines and 16 KB of UTF-8 output by default, with each line clipped at 400
characters and a footer showing how to see more. It is read-only and uses the
existing `beautifulsoup4` dependency. Bounded output is not redaction.

| Need | Flag |
|---|---|
| Next lines / specific range | `--offset N --lines N` |
| End of a log or traceback | `--tail` |
| Search a large JSON/CSV/log | `--grep PATTERN --context N` |
| Rendered HTML evidence | `--html` (visible text; scripts/styles dropped) |
| Failing tests only | `--pytest` |
| More output | `--max-bytes N` (exact UTF-8 bytes of the excerpt) |

Long lines are clipped around a `--grep` match so the match is visible. `--pytest`
keeps the exception tail and the final counts; omitted or truncated output is
marked inline (`lines omitted`, `[truncated]`) rather than silently dropped.

Examples:

```
python -m scripts.peek evidence/arvan/vm/<run>/rendered.html --html
python -m pytest > logs\pytest.log 2>&1
python -m scripts.peek logs\pytest.log --pytest
python -m scripts.peek datasets/offline/<source>/<file>.csv --grep vcpu --context 1
```

`logs/` and `*.log` are Git-ignored. Binary and PDF files are refused rather than
dumped; use the relevant collector to extract their text.

`archive/` preserves 42 historical, one-off exploration scripts. They are not
maintained entry points: many assume old layouts/paths, contact providers, call
paid APIs or write data. Do not import, run or read them as routine context.
Consult specific files only when investigating their original discovery.
