from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

def make_async_url(url: str) -> str:
    """Helper to convert standard postgresql connection URL to async asyncpg URL."""
    if not url:
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_READ_URL = os.getenv("DATABASE_READ_URL", DATABASE_URL)

ASYNC_DATABASE_URL = make_async_url(DATABASE_URL)
ASYNC_DATABASE_READ_URL = make_async_url(DATABASE_READ_URL)

write_engine = create_async_engine(ASYNC_DATABASE_URL, pool_size=20, max_overflow=50)
read_engine = create_async_engine(ASYNC_DATABASE_READ_URL, pool_size=20, max_overflow=50)

AsyncSessionLocalWrite = async_sessionmaker(bind=write_engine, class_=AsyncSession, expire_on_commit=False)
AsyncSessionLocalRead = async_sessionmaker(bind=read_engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocalWrite() as session:
        yield session

async def get_read_db():
    async with AsyncSessionLocalRead() as session:
        yield session
