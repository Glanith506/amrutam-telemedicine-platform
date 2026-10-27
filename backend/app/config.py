from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")
    database_url: str = "postgresql+psycopg://amrutam:amrutam@db:5432/amrutam"
    jwt_secret: str
    encryption_key: str
    jwt_previous_secret: str = ""
    encryption_previous_keys: str = ""
    token_minutes: int = 30
    otel_exporter_otlp_endpoint: str = ""

    @model_validator(mode="after")
    def secure(self):
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must have at least 32 characters")
        return self


settings = Settings()
