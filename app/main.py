from fastapi import FastAPI

from app.api.routes import build_router
from app.config.settings import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.include_router(build_router(settings))
