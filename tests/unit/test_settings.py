from src.core.settings import Settings


def test_settings_loads_defaults():
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url.startswith("redis://")
    assert settings.environment == "development"


def test_settings_reads_env_override(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/testdb")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert settings.database_url == "postgresql+asyncpg://test:test@localhost:5432/testdb"
