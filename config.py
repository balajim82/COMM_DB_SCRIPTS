from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Option 1: full connection URL (credentials embedded) ──────────────
    # postgresql://user:password@host:port/dbname
    DATABASE_URL: Optional[str] = None

    # ── Option 2: individual fields (DATABASE_URL takes priority if set) ──
    DB_HOST: Optional[str] = None
    DB_PORT: int = 5432
    DB_NAME: Optional[str] = None
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_SSLMODE: str = "require"  # "require" for Neon/cloud; "disable" for local

    SQL_OUTPUT_PATH: str = "./generated_sql"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
