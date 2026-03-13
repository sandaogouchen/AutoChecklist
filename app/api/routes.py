from fastapi import APIRouter

from app.config.settings import Settings


def build_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
        }

    return router
