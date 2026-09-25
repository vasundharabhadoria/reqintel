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

# Connects through the Supabase Supavisor SESSION POOLER.
# Pool sized for a student/dev deployment behind a pooler.
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
    Yield a DB session scoped to one transaction, with the RLS bridge set.

    `set_config('app.current_user_id', ..., true)` is used instead of
    `SET LOCAL` because `SET LOCAL` does not accept bind parameters in
    PostgreSQL. The `true` third argument scopes the setting to the
    current transaction only, so it never leaks across pooled connections.
    RLS policies on `projects` etc. read this via `fn_current_user_id()`.
    """

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_user_id', :uid, true)"),
                {"uid": current_user.id},
            )
            yield session