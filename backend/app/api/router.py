from fastapi import APIRouter

from app.api.v1 import (
    auth,
    health,
    processing,
    recordings,
    register,
    sessions,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/v1", tags=["health"])
api_router.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
api_router.include_router(
    processing.router, prefix="/v1/processing", tags=["processing"]
)
api_router.include_router(register.router, prefix="/v1", tags=["register"])
api_router.include_router(users.router, prefix="/v1/users", tags=["users"])
api_router.include_router(recordings.router, prefix="/v1", tags=["recordings"])
api_router.include_router(sessions.router, prefix="/v1", tags=["sessions"])
