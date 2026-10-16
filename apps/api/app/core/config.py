from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", env_ignore_empty=True)

    knowledge_model_path: str = str(ROOT / ".cache/knowledge-model")

    app_env: Literal["development", "test", "production"] = "development"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 55432
    postgres_db: str = "bia_studio"
    postgres_user: str = "bia"
    postgres_password: SecretStr = SecretStr("bia_local_only")
    database_url: SecretStr | None = None
    cors_origins: list[str] = ["http://localhost:3000"]
    enable_demo_auth: bool = False
    demo_admin_token: SecretStr | None = None
    demo_creator_token: SecretStr | None = None
    demo_viewer_token: SecretStr | None = None
    demo_customer_b_token: SecretStr | None = None
    demo_reviewer_token: SecretStr | None = None
    demo_approver_token: SecretStr | None = None
    demo_auditor_token: SecretStr | None = None
    evaluation_timeout_seconds: float = Field(default=60, gt=0, le=90)
    enable_local_runtime: bool = False
    enable_provider_runtime: bool = False
    model_timeout_seconds: float = Field(default=15, gt=0, le=60)
    runtime_timeout_seconds: float = Field(default=30, gt=0, le=120)
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def reject_production_demo(self):
        if self.app_env == "production" and (self.enable_demo_auth or self.enable_local_runtime):
            raise ValueError(
                "Demo authentication and local runtime cannot be enabled in production"
            )
        return self

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            url = make_url(value.get_secret_value())
            if url.drivername != "postgresql+psycopg":
                raise ValueError("DATABASE_URL must use postgresql+psycopg")
        return value

    @property
    def sqlalchemy_url(self) -> URL:
        if self.database_url:
            return make_url(self.database_url.get_secret_value())
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
