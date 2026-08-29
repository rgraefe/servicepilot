from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SERVICEPILOT_",
        env_file=".env",
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    reload: bool = False
    persistence_backend: Literal["memory", "firestore"] = "memory"
    firestore_project: str | None = None
    firestore_database: str = "(default)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
