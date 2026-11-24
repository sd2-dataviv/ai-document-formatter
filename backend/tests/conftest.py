import asyncio
import os

# Configure before any app module is imported (settings are cached on first use).
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://docformatter:docformatter@127.0.0.1:5434/docformatter_test"
)
os.environ["OLLAMA_URL"] = "http://127.0.0.1:9"  # unroutable: tests must never reach a real LLM
os.environ["CHUNK_CHARS"] = "2000"
os.environ["LOG_LEVEL"] = "WARNING"

from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.services.llm import StreamEvent

BACKEND_DIR = Path(__file__).resolve().parent.parent


async def _ensure_test_database(url: str) -> None:
    u = make_url(url)
    conn = await asyncpg.connect(
        user=u.username, password=u.password, host=u.host, port=u.port or 5432, database="postgres"
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", u.database)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{u.database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    asyncio.run(_ensure_test_database(os.environ["DATABASE_URL"]))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["database_url"] = os.environ["DATABASE_URL"]
    # Exercise both directions of the migrations on every run.
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def clean_db() -> None:
    from app.database import engine

    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE documents RESTART IDENTITY CASCADE"))
        await conn.execute(text("DELETE FROM templates WHERE NOT is_builtin"))


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    from app.main import app

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as c:
            yield c


class FakeLLM:
    """Replaces the Ollama client. Records prompts; behaviour is configurable per test."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.content = "# Fake Title\n\nBody text."
        self.delay = 0.0  # seconds to wait before producing content
        self.error: Exception | None = None

    async def __call__(self, system: str, user: str, think: str = "low") -> AsyncIterator[StreamEvent]:
        self.prompts.append(user)
        yield StreamEvent("thinking", "planning…")
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        for piece in (self.content[: len(self.content) // 2], self.content[len(self.content) // 2 :]):
            yield StreamEvent("content", piece)


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr("app.jobs.stream_chat", fake)
    return fake


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch):
    """Mutable view of app settings; changes are reverted after the test."""
    from app.config import get_settings

    s = get_settings()

    class _Proxy:
        def __setattr__(self, key: str, value) -> None:
            monkeypatch.setattr(s, key, value)

        def __getattr__(self, key: str):
            return getattr(s, key)

    return _Proxy()
