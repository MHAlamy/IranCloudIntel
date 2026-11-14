# Iranian Cloud Intelligence Dashboard

A personal competitive-intelligence dashboard for Iranian cloud services:
collects, validates and compares official public pricing (VM, Object Storage,
CDN) across a small set of providers, keeping historical observations and
source evidence.

See `PROJECT_GUIDE.md` for the full specification and `v1_milestones.md` for
the V1 milestone plan.

## Status

Planning / early development — Milestone 1 (local environment preparation).

## Local development (Windows)

Requires Python 3.14 (native Windows) and Git.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests
```

Copy `.env.example` to `.env` and fill in real values before any live API use.
Never commit `.env`.
