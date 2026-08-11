from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session

router = APIRouter()


@router.get("/health")
async def health(
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "run_id": request.state.run_id}
