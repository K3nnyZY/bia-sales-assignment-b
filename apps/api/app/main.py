from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.agents.routes import router as agents_router
from app.api.health import router as health_router
from app.catalogs.routes import router as catalogs_router
from app.core.config import Settings
from app.db.session import build_engine
from app.runtime.routes import router as runtime_router


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = build_engine(config)
        try:
            yield
        finally:
            app.state.engine.dispose()

    app = FastAPI(title="BIA Agent Studio API", version="0.3.0", lifespan=lifespan)
    app.state.settings = config

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "CONSTRAINT_CONFLICT",
                    "message": "Duplicate, referenced or immutable resource; "
                    "no change was committed",
                }
            },
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.include_router(health_router)
    app.include_router(catalogs_router)
    app.include_router(agents_router)
    app.include_router(runtime_router)
    return app


app = create_app()
