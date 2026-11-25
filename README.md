# Iranian Cloud Intelligence Dashboard

A personal Persian-language dashboard for comparing Iranian cloud prices, with
SQLite history and source evidence. Covers VM, Object Storage, PaaS/CNAP, DBaaS
and KaaS. Darkube deployment is planned, not yet implemented.

## Run locally on Windows

With Python 3.14 and Git, run these commands from the repository root. No WSL or
local Docker is required.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. The homepage links to each comparison page;
`/status` shows collection health. Tests run offline by default. Browser tests
are opt-in (`-m browser`) and require an installed Chromium or Edge.

## Collect and inspect data

For collectors that need credentials, copy `.env.example` to `.env` and set the
values privately. Live collection can incur AIaaS charges; get approval first.
To collect one source and inspect the database:

```powershell
.\.venv\Scripts\python.exe -m collectors.cli --source liara_vm_cloud_server
.\.venv\Scripts\python.exe -m scripts.inspect_data summary
```

The inspection command is read-only. Don't commit `.env`, `data/`, or `evidence/`.
Back up the database before running a release with new migrations.

## Further reading

- [Milestones](MILESTONES.md): Darkube rollout and what's next.
- [Project guide](PROJECT_GUIDE.md): architecture and dashboard design.
- [Pricing guide](price_gathering_guide.md): collection and comparison rules.
- [Code map](docs/CODE_MAP.md) and [inspection tools](scripts/README.md).
