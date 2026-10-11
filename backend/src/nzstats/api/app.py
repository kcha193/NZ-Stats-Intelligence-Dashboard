from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from nzstats import __version__
from nzstats.api.routes import router
from nzstats.config import Settings, load_settings
from nzstats.runtime import Runtime, build_adapters, build_runtime
from nzstats.store.db import connect, migrate

log = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serve the built SPA; unknown non-asset paths fall back to index.html for client routing."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def create_app(
    settings: Settings | None = None,
    *,
    start_scheduler: bool = False,
    runtime: Runtime | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    migrate(connect(settings.db_path))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        if start_scheduler:
            from nzstats.scheduler.jobs import build_scheduler, schedule_startup_tasks

            rt = runtime or build_runtime(settings)
            scheduler = build_scheduler(rt)
            schedule_startup_tasks(scheduler, rt)
            scheduler.start()
            log.info("scheduler started with jobs %s", [j.id for j in scheduler.get_jobs()])
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="NZ Stats Intelligence Dashboard", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.analysable_slugs = set(build_adapters(settings))
    app.include_router(router, prefix="/api")

    static = settings.static_dir
    if static and Path(static).is_dir():
        app.mount("/", SPAStaticFiles(directory=str(static), html=True), name="spa")
    return app
