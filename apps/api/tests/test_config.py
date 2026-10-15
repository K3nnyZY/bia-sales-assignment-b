import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def test_environment_overrides_dotenv(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert Settings(_env_file=None).sqlalchemy_url.host == "postgres"


def test_password_is_encoded_without_leaking(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Settings(_env_file=None, postgres_password="p@ss:/%word")
    assert config.sqlalchemy_url.password == "p@ss:/%word"
    assert "p@ss" not in repr(config)


def test_full_url_override():
    config = Settings(
        _env_file=None,
        database_url=SecretStr("postgresql+psycopg://user:secret@db.example:5433/custom"),
    )
    assert config.sqlalchemy_url.host == "db.example"
    assert config.sqlalchemy_url.database == "custom"
    assert "secret" not in repr(config)


def test_rejects_unsupported_database_driver():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite:///test.db")
