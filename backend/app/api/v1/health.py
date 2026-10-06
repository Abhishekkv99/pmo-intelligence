from fastapi import APIRouter, Request

from app.rate_limiter import limiter

router = APIRouter()


@router.get("/health")
@limiter.exempt  # type: ignore[untyped-decorator]
async def health_check(request: Request) -> dict[str, str]:
    return {"status": "healthy", "service": "pmo-intelligence-api"}
