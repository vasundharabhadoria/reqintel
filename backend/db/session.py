from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from auth.schemas import UserResponse
from core.config import settings
from core.dependencies import get_current_user


engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=1800,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db(
    current_user: UserResponse = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide one AsyncSession per request.

    The RLS user context is set inside the session's current transaction.
    RequirementService is responsible for commit/rollback operations.
    """

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "SELECT set_config('app.current_user_id', :uid, true)"
            ),
            {"uid": current_user.id},
        )

        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            if session.in_transaction():
                await session.rollback()