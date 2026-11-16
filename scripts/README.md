# Inspection tools

Use `python -m scripts.inspect_data [summary|providers|runs|verification]`.
Optional `--db PATH --limit N` (default 20, maximum 1000). This command opens
SQLite read-only, does not migrate, and does not call providers or an LLM.

`db_report.py`, `check_db_providers.py` and `check_verification.py` are compatibility
wrappers for that command. Prefer module invocation from the repository root.

`archive/` preserves 42 historical, one-off exploration scripts. They are not
maintained entry points: many assume old layouts/paths, contact providers, call
paid APIs or write data. Do not import, run or read them as routine context.
Consult specific files only when investigating their original discovery.
