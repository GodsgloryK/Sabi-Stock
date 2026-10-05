from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str | None = None
    frontend_origins: str = "http://localhost:5500,http://127.0.0.1:5500"
    jwt_secret_key: str | None = None
    jwt_expire_minutes: int = Field(default=60, gt=0)

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.frontend_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
