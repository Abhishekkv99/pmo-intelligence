from fastapi import APIRouter

from app.api.v1 import auth, health, processing

api_router = APIRouter()

api_router.include_router(health.router, prefix="/v1", tags=["health"])
api_router.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(
    processing.router, prefix="/v1/processing", tags=["processing"]
)
