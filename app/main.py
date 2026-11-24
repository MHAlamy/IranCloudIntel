"""FastAPI dashboard (Persian, RTL) for the Cloud Intelligence project."""

from __future__ import annotations

import os
import sys
from pathlib import Path


from dotenv import load_dotenv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, Query, Request  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

from config.loader import load_products  # noqa: E402
from app.data import (  # noqa: E402
    BASIS_LABELS_FA,
    OS_BASIS_LABELS_FA,
    SIZE_LABELS_FA,
    TIER_LABELS_FA,
    VERIFICATION_LABELS_FA,
    build_dbaas_view,
    build_kaas_view,
    build_os_view,
    build_paas_view,
    build_status_view,
    build_vm_view,
)
from app.benchmark_view import build_os_benchmark_view  # noqa: E402
from storage.repository import Repository  # noqa: E402
from util.format import format_number, format_toman  # noqa: E402
from util.jalali import format_jalali  # noqa: E402

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

DEFAULT_DB = ROOT / "data" / "cloud_intel.db"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["toman"] = lambda v: format_toman(v) if v is not None else "—"
templates.env.filters["pnum"] = format_number
templates.env.filters["jalali"] = lambda v: format_jalali(v) if v else "—"
templates.env.filters["jalali_date"] = lambda v: format_jalali(v, with_time=False) if v else "—"


def create_app(db_path: str | Path | None = None) -> FastAPI:
    db_path = Path(db_path or os.getenv("CLOUD_INTEL_DB", DEFAULT_DB))
    app = FastAPI(title="Cloud Intelligence", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(
            request, "home.html", {"catalog": load_products()}
        )

    @app.get("/vm", response_class=HTMLResponse)
    def vm(request: Request, tier: str = "standard", size: str = "medium"):
        if tier not in TIER_LABELS_FA:
            tier = "standard"
        if size not in SIZE_LABELS_FA:
            size = "medium"
        repo = Repository(db_path)
        try:
            view = build_vm_view(repo, tier, size)
            view["freshness"] = repo.freshness("vm")
        finally:
            repo.close()
        return templates.TemplateResponse(
            request,
            "vm.html",
            {
                "view": view,
                "tiers": TIER_LABELS_FA,
                "sizes": SIZE_LABELS_FA,
                "basis_labels": BASIS_LABELS_FA,
                "verification_labels": VERIFICATION_LABELS_FA,
            },
        )

    @app.get("/object-storage", response_class=HTMLResponse)
    def object_storage(request: Request, scenario: str | None = None):
        repo = Repository(db_path)
        try:
            view = build_os_view(repo, scenario)
            view["freshness"] = repo.freshness("object_storage")
        finally:
            repo.close()
        return templates.TemplateResponse(
            request,
            "os.html",
            {
                "view": view,
                "basis_labels": OS_BASIS_LABELS_FA,
                "benchmark": build_os_benchmark_view(),
            },
        )

    @app.get("/paas", response_class=HTMLResponse)
    def paas(request: Request, size: str = "s1"):
        repo = Repository(db_path)
        try:
            view = build_paas_view(repo, size)
            view["freshness"] = repo.freshness("paas")
        finally:
            repo.close()
        return templates.TemplateResponse(
            request,
            "paas.html",
            {"view": view, "basis_labels": BASIS_LABELS_FA},
        )

    @app.get("/dbaas", response_class=HTMLResponse)
    def dbaas(
        request: Request,
        infra_class: str = Query("local", alias="class"),
        size: str = "small",
    ):
        repo = Repository(db_path)
        try:
            view = build_dbaas_view(repo, infra_class, size)
            view["freshness"] = repo.freshness("dbaas")
        finally:
            repo.close()
        return templates.TemplateResponse(
            request,
            "dbaas.html",
            {"view": view, "basis_labels": BASIS_LABELS_FA},
        )

    @app.get("/kaas", response_class=HTMLResponse)
    def kaas(request: Request, scenario: str = "small"):
        repo = Repository(db_path)
        try:
            view = build_kaas_view(repo, scenario)
            view["freshness"] = repo.freshness("kaas")
        finally:
            repo.close()
        return templates.TemplateResponse(
            request,
            "kaas.html",
            {"view": view, "basis_labels": BASIS_LABELS_FA},
        )

    @app.get("/plan/{offering_id}", response_class=HTMLResponse)
    def plan(request: Request, offering_id: int):
        repo = Repository(db_path)
        try:
            offering = repo.get_offering(offering_id)
            history = repo.offering_history(offering_id)
        finally:
            repo.close()
        return templates.TemplateResponse(
            request,
            "plan.html",
            {"offering": offering, "history": history,
             "verification_labels": VERIFICATION_LABELS_FA},
        )

    @app.get("/status", response_class=HTMLResponse)
    def status(request: Request):
        repo = Repository(db_path)
        try:
            view = build_status_view(repo)
        finally:
            repo.close()
        return templates.TemplateResponse(request, "status.html", {"view": view})

    return app


app = create_app()
