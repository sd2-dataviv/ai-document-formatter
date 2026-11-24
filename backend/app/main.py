import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .database import SessionLocal, engine
from .jobs import job_manager, recover_interrupted_jobs
from .logging_config import setup_logging
from .middleware import RequestContextMiddleware
from .routers import documents, extract, health, jobs, templates
from .seed import seed_templates
from .services.export import warm_up as warm_up_exporters

settings = get_settings()
setup_logging(settings.log_level, settings.json_logs)
log = logging.getLogger("docformatter")


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info(
        "starting DocFormatter %s (env=%s, model=%s, llm=%s)",
        __version__,
        settings.environment,
        settings.ollama_model,
        settings.ollama_url,
    )
    # Schema is managed by Alembic (`alembic upgrade head`); here we only seed and recover.
    async with SessionLocal() as session:
        await seed_templates(session)
    recovered = await recover_interrupted_jobs()
    if recovered:
        log.warning("marked %d interrupted job(s) as failed", recovered)
    await run_in_threadpool(warm_up_exporters)
    job_manager.start(settings.max_concurrent_jobs)
    yield
    log.info("shutting down")
    await job_manager.shutdown()
    await engine.dispose()


app = FastAPI(
    title="DocFormatter AI",
    version=__version__,
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["Content-Disposition", "X-Request-ID"],
    )
app.add_middleware(RequestContextMiddleware)

for r in (health, templates, documents, jobs, extract):
    app.include_router(r.router)
