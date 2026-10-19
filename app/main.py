from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.upload_routes import router as upload_router
from app.core.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Resumable Upload POC",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(upload_router)
    return application


app = create_app()
