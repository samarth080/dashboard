# M0 Repository Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the monorepo skeleton (FastAPI, Next.js, Celery/Redis, Postgres, LLM abstraction with MockLLM) that later milestones build domain logic on top of — no product features, just a working, tested, observable foundation.

**Architecture:** Single `uv`-managed Python project (non-packaged, run via `uv run` from repo root) containing `src/` (core settings, logging, db, llm), `services/api` (FastAPI), `services/worker` (Celery). A `runs` table and `llm_calls` table are the only schema. `apps/web` is a separate Next.js/TypeScript app. Everything runs together via Docker Compose (postgres+pgvector, redis, api, worker, web).

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2 (async, asyncpg) + Alembic, Celery + Redis, pytest/pytest-asyncio, ruff, pyright, pre-commit, Next.js 15 + TypeScript, Docker Compose.

---

## Design reference

Full design: `docs/superpowers/specs/2026-08-11-m0-repository-foundation-design.md`

## File Structure

```
pyproject.toml
.env.example
.gitignore
.pre-commit-config.yaml
docker-compose.yml
Dockerfile
alembic.ini
alembic/env.py
alembic/script.py.mako
alembic/versions/0001_initial.py
src/core/settings.py
src/core/logging.py
src/db/base.py
src/db/models.py
src/db/session.py
src/llm/protocol.py
src/llm/mock.py
src/llm/logging.py
services/api/main.py
services/api/routes/health.py
services/worker/celery_app.py
services/worker/tasks.py
apps/web/package.json
apps/web/tsconfig.json
apps/web/next.config.ts
apps/web/lib/nav.ts
apps/web/app/layout.tsx
apps/web/app/page.tsx
apps/web/app/content/page.tsx
apps/web/app/research/page.tsx
apps/web/app/network/page.tsx
apps/web/app/jobs/page.tsx
apps/web/app/applications/page.tsx
apps/web/app/analytics/page.tsx
apps/web/app/automations/page.tsx
apps/web/app/settings/page.tsx
apps/web/Dockerfile
tests/unit/test_settings.py
tests/unit/test_logging.py
tests/unit/test_mock_llm.py
tests/integration/conftest.py
tests/integration/test_migration.py
tests/integration/test_health.py
tests/integration/test_llm_call_logging.py
tests/integration/test_worker_ping.py
HANDOVER.md
```

---

### Task 1: Project scaffold and tooling config

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "career-engine"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "psycopg2-binary>=2.9",
    "alembic>=1.14",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "celery[redis]>=5.4",
    "redis>=5.2",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    "ruff>=0.7",
    "pyright>=1.1",
    "pre-commit>=4.0",
]

[tool.uv]
package = false

[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pyright]
include = ["src", "services", "tests"]
pythonVersion = "3.12"
typeCheckingMode = "basic"
```

- [ ] **Step 2: Write `.env.example`**

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/engine
REDIS_URL=redis://localhost:6379/0
ENVIRONMENT=development
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

- [ ] **Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
.mypy_cache/
*.egg-info/
.env
node_modules/
.next/
dist/
build/
.DS_Store
```

- [ ] **Step 4: Install dependencies and verify environment**

Run: `uv sync`
Expected: creates `.venv/` and `uv.lock`, exits 0.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example .gitignore uv.lock
git commit -m "chore: scaffold uv project and tooling config"
```

---

### Task 2: Core settings

**Files:**
- Create: `src/core/__init__.py`
- Create: `src/core/settings.py`
- Test: `tests/unit/test_settings.py`
- Create: `tests/unit/__init__.py`, `tests/__init__.py`, `src/__init__.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_settings.py`:
```python
from src.core.settings import Settings


def test_settings_loads_defaults():
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url.startswith("redis://")
    assert settings.environment == "development"


def test_settings_reads_env_override(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/testdb")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+asyncpg://test:test@localhost:5432/testdb"
```

- [ ] **Step 2: Create empty `__init__.py` files and run test to verify it fails**

```bash
mkdir -p src/core tests/unit
touch src/__init__.py src/core/__init__.py tests/__init__.py tests/unit/__init__.py
```

Run: `uv run pytest tests/unit/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.settings'`

- [ ] **Step 3: Write minimal implementation**

`src/core/settings.py`:
```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/engine"
    redis_url: str = "redis://localhost:6379/0"
    environment: str = "development"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_settings.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/__init__.py src/core/__init__.py src/core/settings.py tests/__init__.py tests/unit/__init__.py tests/unit/test_settings.py
git commit -m "feat(core): add pydantic-settings Settings"
```

---

### Task 3: Structured logging with run_id propagation

**Files:**
- Create: `src/core/logging.py`
- Test: `tests/unit/test_logging.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_logging.py`:
```python
import json
import logging

from src.core.logging import JSONFormatter, run_id_var, set_run_id


def test_json_formatter_includes_run_id_and_message():
    set_run_id("abc-123")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    formatted = JSONFormatter().format(record)
    payload = json.loads(formatted)
    assert payload["run_id"] == "abc-123"
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    run_id_var.set(None)


def test_json_formatter_run_id_is_none_by_default():
    run_id_var.set(None)
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="no run", args=(), exc_info=None,
    )
    payload = json.loads(JSONFormatter().format(record))
    assert payload["run_id"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_logging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.logging'`

- [ ] **Step 3: Write minimal implementation**

`src/core/logging.py`:
```python
import contextvars
import json
import logging

run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": run_id_var.get(),
        }
        return json.dumps(payload)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


def set_run_id(run_id: str) -> None:
    run_id_var.set(run_id)


def get_run_id() -> str | None:
    return run_id_var.get()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_logging.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/core/logging.py tests/unit/test_logging.py
git commit -m "feat(core): add structured JSON logging with run_id propagation"
```

---

### Task 4: Database base, models, session

**Files:**
- Create: `src/db/__init__.py`
- Create: `src/db/base.py`
- Create: `src/db/models.py`
- Create: `src/db/session.py`

No standalone unit test here — correctness is verified against a real Postgres in Task 5's integration test. This task is scaffolding only.

- [ ] **Step 1: Write `src/db/base.py`**

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 2: Write `src/db/models.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid.uuid4, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    llm_calls: Mapped[list["LLMCall"]] = relationship(back_populates="run")


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    input_tokens: Mapped[int] = mapped_column(nullable=False)
    output_tokens: Mapped[int] = mapped_column(nullable=False)
    latency_ms: Mapped[int] = mapped_column(nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    run: Mapped["Run"] = relationship(back_populates="llm_calls")
```

- [ ] **Step 3: Write `src/db/session.py`**

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.settings import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
```

- [ ] **Step 4: Create `src/db/__init__.py`**

```bash
touch src/db/__init__.py
```

- [ ] **Step 5: Verify the module imports cleanly**

Run: `uv run python -c "from src.db.models import Run, LLMCall; from src.db.session import get_session; print('ok')"`
Expected: prints `ok`

- [ ] **Step 6: Commit**

```bash
git add src/db/
git commit -m "feat(db): add SQLAlchemy base, Run/LLMCall models, async session factory"
```

---

### Task 5: Alembic setup and initial migration

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_initial.py`
- Test: `tests/integration/conftest.py`, `tests/integration/test_migration.py`, `tests/integration/__init__.py`

This task requires a running Postgres. Start it first:

Run: `docker run -d --name m0-test-pg -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=engine -p 5432:5432 pgvector/pgvector:pg16`
Expected: container starts; wait ~5s for it to accept connections.

- [ ] **Step 1: Write `alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 2: Write `alembic/env.py`**

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.core.settings import get_settings
from src.db import models  # noqa: F401  ensures models register on Base.metadata
from src.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
sync_url = settings.database_url.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Write `alembic/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Write `alembic/versions/0001_initial.py`**

```python
"""initial schema: runs, llm_calls

Revision ID: 0001
Revises:
Create Date: 2026-08-11

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_calls")
    op.drop_table("runs")
```

- [ ] **Step 5: Apply the migration and verify**

Run: `uv run alembic upgrade head`
Expected: exits 0, logs `Running upgrade  -> 0001, initial schema: runs, llm_calls`

- [ ] **Step 6: Write integration test scaffolding**

`tests/integration/__init__.py`: empty file.

`tests/integration/conftest.py`:
```python
import subprocess

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import async_session_factory


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True)
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
        await session.rollback()
```

`tests/integration/test_migration.py`:
```python
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_runs_and_llm_calls_tables_exist(db_session: AsyncSession):
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    )
    tables = {row[0] for row in result}
    assert "runs" in tables
    assert "llm_calls" in tables
```

- [ ] **Step 7: Run the integration test**

Run: `uv run pytest tests/integration/test_migration.py -v`
Expected: PASS (1 test)

- [ ] **Step 8: Commit**

```bash
git add alembic.ini alembic/ tests/integration/__init__.py tests/integration/conftest.py tests/integration/test_migration.py
git commit -m "feat(db): add Alembic setup and initial runs/llm_calls migration"
```

---

### Task 6: LLM client protocol and MockLLM

**Files:**
- Create: `src/llm/__init__.py`
- Create: `src/llm/protocol.py`
- Create: `src/llm/mock.py`
- Test: `tests/unit/test_mock_llm.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_mock_llm.py`:
```python
import pytest
from pydantic import BaseModel

from src.llm.mock import MockLLM


class DummySchema(BaseModel):
    name: str = "default"


@pytest.mark.asyncio
async def test_generate_returns_llm_result():
    llm = MockLLM()
    result = await llm.generate("hello", prompt_version="v1")
    assert result.model == "mock-llm"
    assert result.prompt_version == "v1"
    assert result.cost_usd == 0.0
    assert result.text.startswith("[mock response")
    assert result.input_tokens == 1
    assert result.output_tokens > 0


@pytest.mark.asyncio
async def test_structured_returns_schema_instance():
    llm = MockLLM()
    result = await llm.structured("hello", prompt_version="v1", schema=DummySchema)
    assert isinstance(result, DummySchema)
    assert result.name == "default"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_mock_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.llm'`

- [ ] **Step 3: Write minimal implementation**

`src/llm/__init__.py`: empty file.

`src/llm/protocol.py`:
```python
from typing import Protocol

from pydantic import BaseModel


class LLMResult(BaseModel):
    text: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float


class LLMClient(Protocol):
    async def generate(self, prompt: str, *, prompt_version: str) -> LLMResult: ...

    async def structured(
        self, prompt: str, *, prompt_version: str, schema: type[BaseModel]
    ) -> BaseModel: ...
```

`src/llm/mock.py`:
```python
import time

from pydantic import BaseModel

from src.llm.protocol import LLMResult


class MockLLM:
    model_name = "mock-llm"

    async def generate(self, prompt: str, *, prompt_version: str) -> LLMResult:
        start = time.perf_counter()
        text = f"[mock response to: {prompt[:50]}]"
        latency_ms = int((time.perf_counter() - start) * 1000)
        return LLMResult(
            text=text,
            model=self.model_name,
            prompt_version=prompt_version,
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            latency_ms=latency_ms,
            cost_usd=0.0,
        )

    async def structured(
        self, prompt: str, *, prompt_version: str, schema: type[BaseModel]
    ) -> BaseModel:
        return schema()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_mock_llm.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/llm/__init__.py src/llm/protocol.py src/llm/mock.py tests/unit/test_mock_llm.py
git commit -m "feat(llm): add LLMClient protocol and MockLLM"
```

---

### Task 7: Persisting LLM calls

**Files:**
- Create: `src/llm/logging.py`
- Test: `tests/integration/test_llm_call_logging.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_llm_call_logging.py`:
```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Run
from src.llm.logging import log_llm_call
from src.llm.mock import MockLLM


@pytest.mark.asyncio
async def test_mock_llm_call_is_logged(db_session: AsyncSession):
    run = Run()
    db_session.add(run)
    await db_session.flush()

    llm = MockLLM()
    result = await llm.generate("hello world", prompt_version="v1")
    call = await log_llm_call(db_session, run, result)

    assert call.id is not None
    assert call.run_id == run.id
    assert call.model == "mock-llm"
    assert call.cost_usd == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_llm_call_logging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.llm.logging'`

- [ ] **Step 3: Write minimal implementation**

`src/llm/logging.py`:
```python
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import LLMCall, Run
from src.llm.protocol import LLMResult


async def log_llm_call(session: AsyncSession, run: Run, result: LLMResult) -> LLMCall:
    call = LLMCall(
        run_id=run.id,
        model=result.model,
        prompt_version=result.prompt_version,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
        cost_usd=result.cost_usd,
    )
    session.add(call)
    await session.flush()
    await session.refresh(call)
    return call
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_llm_call_logging.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add src/llm/logging.py tests/integration/test_llm_call_logging.py
git commit -m "feat(llm): persist LLM calls to llm_calls table"
```

---

### Task 8: FastAPI app with health route

**Files:**
- Create: `services/__init__.py`, `services/api/__init__.py`, `services/api/routes/__init__.py`
- Create: `services/api/main.py`
- Create: `services/api/routes/health.py`
- Test: `tests/integration/test_health.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_health.py`:
```python
import pytest
from httpx import ASGITransport, AsyncClient

from services.api.main import app


@pytest.mark.asyncio
async def test_health_returns_ok_with_run_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "run_id" in body and body["run_id"]
    assert "X-Run-Id" in response.headers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services'`

- [ ] **Step 3: Write minimal implementation**

`services/__init__.py`, `services/api/__init__.py`, `services/api/routes/__init__.py`: empty files.

`services/api/routes/health.py`:
```python
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session

router = APIRouter()


@router.get("/health")
async def health(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "run_id": request.state.run_id}
```

`services/api/main.py`:
```python
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from services.api.routes.health import router as health_router
from src.core.logging import configure_logging, set_run_id

configure_logging()

app = FastAPI(title="Personal Career Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def run_id_middleware(request: Request, call_next):
    run_id = str(uuid.uuid4())
    set_run_id(run_id)
    request.state.run_id = run_id
    response = await call_next(request)
    response.headers["X-Run-Id"] = run_id
    return response


app.include_router(health_router, prefix="/api")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_health.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Manually verify the server boots**

Run: `uv run uvicorn services.api.main:app --port 8000 &` then `curl -s http://localhost:8000/api/health`
Expected: JSON body `{"status": "ok", "run_id": "<uuid>"}`. Stop the server afterward (`kill %1`).

- [ ] **Step 6: Commit**

```bash
git add services/__init__.py services/api/ tests/integration/test_health.py
git commit -m "feat(api): add FastAPI app with health route and run_id middleware"
```

---

### Task 9: Celery worker with ping task

**Files:**
- Create: `services/worker/__init__.py`
- Create: `services/worker/celery_app.py`
- Create: `services/worker/tasks.py`
- Test: `tests/integration/test_worker_ping.py`

This task requires Redis running: `docker run -d --name m0-test-redis -p 6379:6379 redis:7-alpine`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_worker_ping.py`:
```python
import subprocess
import time

import pytest

from services.worker.celery_app import celery_app
from services.worker.tasks import ping


@pytest.fixture(scope="module")
def celery_worker_process():
    proc = subprocess.Popen(
        [
            "uv", "run", "celery", "-A", "services.worker.celery_app", "worker",
            "--loglevel=info", "--pool=solo",
        ]
    )
    for _ in range(30):
        if celery_app.control.ping(timeout=1):
            break
        time.sleep(1)
    else:
        proc.terminate()
        raise RuntimeError("celery worker did not start in time")
    yield proc
    proc.terminate()
    proc.wait(timeout=10)


def test_ping_task_round_trips_through_redis(celery_worker_process):
    async_result = ping.delay()
    assert async_result.get(timeout=10) == "pong"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_worker_ping.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.worker'`

- [ ] **Step 3: Write minimal implementation**

`services/worker/__init__.py`: empty file.

`services/worker/celery_app.py`:
```python
from celery import Celery

from src.core.settings import get_settings

settings = get_settings()

celery_app = Celery("engine_worker", broker=settings.redis_url, backend=settings.redis_url)
```

`services/worker/tasks.py`:
```python
from services.worker.celery_app import celery_app


@celery_app.task(name="ping")
def ping() -> str:
    return "pong"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_worker_ping.py -v -s`
Expected: PASS (1 test) — takes a few seconds while the worker subprocess starts.

- [ ] **Step 5: Commit**

```bash
git add services/worker/ tests/integration/test_worker_ping.py
git commit -m "feat(worker): add Celery app and ping task"
```

---

### Task 10: Docker Compose and Dockerfiles

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Write root `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --no-install-project
COPY . .
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: engine
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/engine
      REDIS_URL: redis://redis:6379/0
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    volumes:
      - .:/app

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run celery -A services.worker.celery_app worker --loglevel=info --pool=solo
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/engine
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    volumes:
      - .:/app

  web:
    build:
      context: apps/web
      dockerfile: Dockerfile
    command: npm run dev
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    ports:
      - "3000:3000"
    volumes:
      - ./apps/web:/app
      - /app/node_modules

volumes:
  postgres_data:
```

- [ ] **Step 3: Commit**

(The `web` build context doesn't exist yet — that's fine, this commits config; Task 11 adds `apps/web`. Full-stack verification happens at the end of Task 11.)

```bash
git add Dockerfile docker-compose.yml
git commit -m "chore: add Dockerfile and docker-compose stack definition"
```

---

### Task 11: Next.js web skeleton

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/next.config.ts`
- Create: `apps/web/lib/nav.ts`
- Create: `apps/web/app/layout.tsx`
- Create: `apps/web/app/page.tsx`
- Create: `apps/web/app/content/page.tsx`
- Create: `apps/web/app/research/page.tsx`
- Create: `apps/web/app/network/page.tsx`
- Create: `apps/web/app/jobs/page.tsx`
- Create: `apps/web/app/applications/page.tsx`
- Create: `apps/web/app/analytics/page.tsx`
- Create: `apps/web/app/automations/page.tsx`
- Create: `apps/web/app/settings/page.tsx`
- Create: `apps/web/Dockerfile`

- [ ] **Step 1: Write `apps/web/package.json`**

```json
{
  "name": "web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "^15.0.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "@types/node": "^22.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0"
  }
}
```

- [ ] **Step 2: Write `apps/web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Write `apps/web/next.config.ts`**

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

export default nextConfig;
```

- [ ] **Step 4: Write `apps/web/lib/nav.ts`**

```typescript
export interface NavItem {
  label: string;
  href: string;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Today", href: "/" },
  { label: "Content", href: "/content" },
  { label: "Research", href: "/research" },
  { label: "Network", href: "/network" },
  { label: "Jobs", href: "/jobs" },
  { label: "Applications", href: "/applications" },
  { label: "Analytics", href: "/analytics" },
  { label: "Automations", href: "/automations" },
  { label: "Settings", href: "/settings" },
];
```

- [ ] **Step 5: Write `apps/web/app/layout.tsx`**

```tsx
import Link from "next/link";
import { NAV_ITEMS } from "@/lib/nav";

export const metadata = {
  title: "Career Engine",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav style={{ display: "flex", gap: "1rem", padding: "1rem", borderBottom: "1px solid #ccc" }}>
          {NAV_ITEMS.map((item) => (
            <Link key={item.href} href={item.href}>
              {item.label}
            </Link>
          ))}
        </nav>
        <main style={{ padding: "1rem" }}>{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 6: Write `apps/web/app/page.tsx` (Today page, calls health)**

```tsx
"use client";

import { useEffect, useState } from "react";

interface HealthResponse {
  status: string;
  run_id: string;
}

export default function TodayPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    fetch(`${apiUrl}/api/health`)
      .then((res) => res.json())
      .then(setHealth)
      .catch((err) => setError(String(err)));
  }, []);

  return (
    <div>
      <h1>Today</h1>
      {error && <p>API error: {error}</p>}
      {health && (
        <p>
          API status: {health.status} (run_id: {health.run_id})
        </p>
      )}
      {!health && !error && <p>Checking API health...</p>}
    </div>
  );
}
```

- [ ] **Step 7: Write the eight placeholder pages**

`apps/web/app/content/page.tsx`:
```tsx
export default function ContentPage() {
  return <h1>Content — coming soon</h1>;
}
```

`apps/web/app/research/page.tsx`:
```tsx
export default function ResearchPage() {
  return <h1>Research — coming soon</h1>;
}
```

`apps/web/app/network/page.tsx`:
```tsx
export default function NetworkPage() {
  return <h1>Network — coming soon</h1>;
}
```

`apps/web/app/jobs/page.tsx`:
```tsx
export default function JobsPage() {
  return <h1>Jobs — coming soon</h1>;
}
```

`apps/web/app/applications/page.tsx`:
```tsx
export default function ApplicationsPage() {
  return <h1>Applications — coming soon</h1>;
}
```

`apps/web/app/analytics/page.tsx`:
```tsx
export default function AnalyticsPage() {
  return <h1>Analytics — coming soon</h1>;
}
```

`apps/web/app/automations/page.tsx`:
```tsx
export default function AutomationsPage() {
  return <h1>Automations — coming soon</h1>;
}
```

`apps/web/app/settings/page.tsx`:
```tsx
export default function SettingsPage() {
  return <h1>Settings — coming soon</h1>;
}
```

- [ ] **Step 8: Write `apps/web/Dockerfile`**

```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]
```

- [ ] **Step 9: Install and manually verify**

Run: `cd apps/web && npm install && npm run dev &`
Then open `http://localhost:3000` — expect the nav shell and "Checking API health..." (or the live health payload if the API from Task 8 is also running on port 8000).
Stop the dev server afterward (`kill %1`), `cd` back to repo root.

- [ ] **Step 10: Full-stack verification**

Run: `docker compose up --build -d`
Expected: all five services (`postgres`, `redis`, `api`, `worker`, `web`) report running via `docker compose ps`.

Run: `docker compose exec api uv run alembic upgrade head`
Expected: exits 0.

Run: `curl -s http://localhost:8000/api/health`
Expected: `{"status": "ok", "run_id": "..."}`

Open `http://localhost:3000` in a browser — Today page shows `API status: ok`.

Run: `docker compose down`

- [ ] **Step 11: Commit**

```bash
git add apps/web
git commit -m "feat(web): add Next.js skeleton with nav shell and health check page"
```

---

### Task 12: Pre-commit hooks

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: pyright
        name: pyright
        entry: uv run pyright
        language: system
        pass_filenames: false
      - id: pytest-unit
        name: pytest (unit)
        entry: uv run pytest tests/unit -q
        language: system
        pass_filenames: false
```

- [ ] **Step 2: Install the hooks and run against all files**

Run: `uv run pre-commit install`
Run: `uv run pre-commit run --all-files`
Expected: ruff, ruff-format, pyright, and pytest-unit hooks all pass (fix any lint/type issues surfaced at this point before proceeding).

- [ ] **Step 3: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "chore: add pre-commit hooks for ruff, pyright, and unit tests"
```

---

### Task 13: Full verification pass and HANDOVER.md

**Files:**
- Create: `HANDOVER.md`

- [ ] **Step 1: Run the full test suite**

Run: `docker compose up -d postgres redis` (integration tests need real Postgres/Redis)
Run: `uv run pytest -v`
Expected: all unit and integration tests pass.

- [ ] **Step 2: Run lint and type checks**

Run: `uv run ruff check .`
Run: `uv run pyright`
Expected: both exit 0.

- [ ] **Step 3: Get the latest commit hash for the handover doc**

Run: `git log --oneline -1`

- [ ] **Step 4: Write `HANDOVER.md`**

```markdown
# HANDOVER

## CURRENT BRANCH
main

## LATEST COMMIT
<paste the hash and message from Step 3>

## MILESTONE STATUS
M0 (Repository Foundation) — COMPLETE

## WHAT EXISTS
- `src/core`: settings (pydantic-settings), structured JSON logging with run_id propagation
- `src/db`: SQLAlchemy 2 async engine/session, `Run` and `LLMCall` models
- `src/llm`: `LLMClient` protocol, `MockLLM`, call-logging helper
- `services/api`: FastAPI app with `GET /api/health`, run_id middleware, CORS for the web app
- `services/worker`: Celery app + `ping` task wired to Redis
- `apps/web`: Next.js/TypeScript nav shell with placeholder pages for every top-level section, Today page wired to `/api/health`
- Alembic migration `0001_initial` creating `runs` and `llm_calls`
- Docker Compose stack (postgres+pgvector, redis, api, worker, web)
- pytest (unit + integration), ruff, pyright, pre-commit all configured and passing

## ARCHITECTURE
See `docs/superpowers/specs/2026-08-11-m0-repository-foundation-design.md`.
Non-packaged uv project (`[tool.uv] package = false`); everything runs via
`uv run` from the repo root so `src`/`services` import as plain packages.

## DATABASE
Tables: `runs` (id, run_id uuid, created_at), `llm_calls` (id, run_id FK,
model, prompt_version, input_tokens, output_tokens, latency_ms, cost_usd,
created_at). One migration: `alembic/versions/0001_initial.py`.

## API ROUTES
- `GET /api/health` — DB connectivity check, returns `{status, run_id}`

## BACKGROUND WORKERS
- Celery app (`services/worker/celery_app.py`) with one task: `ping` → `"pong"`

## TEST STATUS
- unit: passing (`tests/unit/`)
- integration: passing (`tests/integration/`, requires `docker compose up -d postgres redis`)
- lint (ruff): passing
- typecheck (pyright): passing

## PLATFORM CAPABILITIES VERIFIED
None yet — M0 has no external platform integrations. `docs/platform-capabilities.md`
will be populated starting M7 (Integrations) once LinkedIn/X/job-board APIs are
in scope.

## KNOWN LIMITATIONS
- No real LLM provider wired (OpenAI/Anthropic keys accepted in settings but unused) — intentional, deferred until a milestone has an actual caller.
- No domain tables beyond `runs`/`llm_calls` — profile/content/job/network schemas arrive in M1+.
- Integration tests require Docker (Postgres + Redis) running locally; no CI pipeline configured yet.

## ENVIRONMENT VARIABLES
See `.env.example`: `DATABASE_URL`, `REDIS_URL`, `ENVIRONMENT`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.

## HOW TO RUN
```bash
cp .env.example .env
uv sync
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn services.api.main:app --reload &
uv run celery -A services.worker.celery_app worker --loglevel=info --pool=solo &
cd apps/web && npm install && npm run dev
```
Or the full stack: `docker compose up --build`.

## NEXT TASK
M1 — Personal Brain: `UserProfile`, `Interest` graph, `CareerProfile`,
`VoiceProfile`, settings API, memory base tables. Brainstorm and spec this
as its own sub-project before implementing.
```

- [ ] **Step 5: Commit**

```bash
git add HANDOVER.md
git commit -m "docs: add HANDOVER.md for M0 completion"
```

---

## Plan self-review notes

- **Spec coverage:** every success criterion in the design doc maps to a task — compose stack (Task 10–11 verification), migrations (Task 5), `/api/health` (Task 8), nav shell + health page (Task 11), Celery ping (Task 9), MockLLM + llm_calls logging (Tasks 6–7), ruff/pyright/pytest/pre-commit (Task 1, 12, 13).
- **Out-of-scope items confirmed absent:** no domain tables, no extra API routes, no real LLM provider clients anywhere in this plan.
- **Type consistency checked:** `LLMResult` fields match between `protocol.py`, `mock.py`, and `logging.py`; `Run`/`LLMCall` field names match between `models.py`, `0001_initial.py`, and the tests that reference them (`run.id`, `call.run_id`, `call.cost_usd`).
