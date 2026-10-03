"""Application settings loaded from environment variables with safe defaults.

Intentionally dependency-free (plain dataclass) so configuration works before
any optional packages are installed. See .env.example at the repo root for the
supported variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _as_bool(value: str, default: bool = False) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"} if value else default


@dataclass(frozen=True)
class Settings:
    app_name: str = "hackathon-backend"
    version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: tuple[str, ...] = _DEFAULT_CORS_ORIGINS
    metrics_output_dir: Path = Path("data/metrics")
    eval_output_dir: Path = Path("data/evals")
    log_level: str = "INFO"
    log_format: str = "console"
    log_file_enabled: bool = False
    log_file_path: Path = Path("data/logs/app.jsonl")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("APP_HOST", cls.host),
            port=int(os.getenv("APP_PORT", str(cls.port))),
            cors_origins=_split_csv(
                os.getenv("CORS_ORIGINS", ",".join(_DEFAULT_CORS_ORIGINS))
            ),
            metrics_output_dir=Path(
                os.getenv("METRICS_OUTPUT_DIR", str(cls.metrics_output_dir))
            ),
            eval_output_dir=Path(os.getenv("EVAL_OUTPUT_DIR", str(cls.eval_output_dir))),
            log_level=os.getenv("LOG_LEVEL", cls.log_level),
            log_format=os.getenv("LOG_FORMAT", cls.log_format),
            log_file_enabled=_as_bool(
                os.getenv("LOG_FILE_ENABLED", "false"), cls.log_file_enabled
            ),
            log_file_path=Path(os.getenv("LOG_FILE_PATH", str(cls.log_file_path))),
        )


settings = Settings.from_env()
