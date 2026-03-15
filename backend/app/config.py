from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ReviewPro API"
    api_prefix: str = "/api"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./storage/reviewpro.db"
    storage_dir: Path = Path("storage")
    upload_dir_name: str = "uploads"
    page_index_dir_name: str = "page_index"
    llm_api_key: str | None = None
    llm_base_url: str = "https://coding.dashscope.aliyuncs.com/v1"
    llm_model: str = "qwen3.5-plus"
    max_page_budget: int = 20
    max_page_budget_ratio: float = 0.3
    min_review_pages: int = 4
    max_preview_chars: int = 800

    model_config = SettingsConfigDict(
        env_prefix="REVIEWPRO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def upload_dir(self) -> Path:
        return self.storage_dir / self.upload_dir_name

    @property
    def page_index_dir(self) -> Path:
        return self.storage_dir / self.page_index_dir_name


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.page_index_dir.mkdir(parents=True, exist_ok=True)
    return settings


