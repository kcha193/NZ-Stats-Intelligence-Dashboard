from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
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


def _hangup_as_terminate() -> Callable[[], None]:
    """Closing the terminal sends SIGHUP, which would kill the process with no clean-stop record. Treat it like SIGTERM
    (uvicorn's graceful path) unless the caller chose otherwise (`nohup` ignores it). Returns the undo."""
    hup = getattr(signal, "SIGHUP", None)
    if hup is None or threading.current_thread() is not threading.main_thread():
        return lambda: None
    if signal.getsignal(hup) != signal.SIG_DFL:
        return lambda: None
    signal.signal(hup, lambda *_: signal.raise_signal(signal.SIGTERM))
    return lambda: signal.signal(hup, signal.SIG_DFL)


def create_app(
    settings: Settings | None = None,
    *,
    start_scheduler: bool = False,
    runtime: Runtime | None = None,
    routers: Sequence[APIRouter] = (),
    record_ops: bool = False,
    capabilities: Mapping[str, bool] | None = None,
) -> FastAPI:
    """The API and built UI. `routers` are extra `/api` routes (the CLI adds research); they come before the
    catch-all, so the snapshot exporter, which passes none, can never serve them.

    `record_ops` (the CLI's `serve` sets it) makes the process record its heartbeat, whether the scheduler is on and its
    job states in the database, so `nzstats status` can tell a stopped, a deliberately idle and a stalled dashboard
    apart. `capabilities` are feature flags the UI may ask about (`/api/capabilities`); none are on by default."""
    settings = settings or load_settings()
    bootstrap = connect(settings.db_path)
    try:
        migrate(bootstrap)
    finally:
        bootstrap.close()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        recorder = heartbeat = None
        undo_hangup = lambda: None  # noqa: E731
        if record_ops:
            from nzstats.ops.recorder import HeartbeatThread, OpsRecorder
            from nzstats.ops.thresholds import Thresholds

            recorder = OpsRecorder(
                settings.db_path, scheduler_enabled=start_scheduler, version=__version__
            )
            recorder.start()
            heartbeat = HeartbeatThread(recorder, Thresholds().heartbeat_interval_seconds)
            heartbeat.start()
            undo_hangup = _hangup_as_terminate()
        scheduler = None
        try:
            if start_scheduler:
                from nzstats.ops.recorder import SCHEDULER_EVENTS
                from nzstats.scheduler.jobs import build_scheduler, schedule_startup_tasks

                rt = runtime or build_runtime(settings)
                scheduler = build_scheduler(rt)
                if recorder is not None:
                    scheduler.add_listener(recorder.on_scheduler_event, SCHEDULER_EVENTS)
                schedule_startup_tasks(scheduler, rt)
                scheduler.start()
                log.info("scheduler started with jobs %s", [j.id for j in scheduler.get_jobs()])
            yield
        finally:
            try:
                if scheduler is not None and scheduler.running:
                    scheduler.shutdown(wait=False)
            finally:
                undo_hangup()
                if heartbeat is not None:
                    heartbeat.stop()
                if recorder is not None:
                    recorder.stop()

    app = FastAPI(title="NZ Stats Intelligence Dashboard", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.capabilities = dict(capabilities or {})
    app.state.analysable_slugs = set(build_adapters(settings))
    for extra in routers:
        app.include_router(extra, prefix="/api")
    app.include_router(router, prefix="/api")

    static = settings.static_dir
    if static and Path(static).is_dir():
        app.mount("/", SPAStaticFiles(directory=str(static), html=True), name="spa")
    return app
