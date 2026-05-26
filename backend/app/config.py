"""Runtime configuration loaded from environment variables / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM (Volcengine Ark) ---
    ark_api_key: str = ""
    ark_model_id: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_timeout: float = 60.0
    ark_max_retries: int = 2
    ark_use_json_mode: bool = False
    volc_mock: bool = False

    # --- Search backend ---
    search_provider: Literal["tavily", "serper", "bing", "none"] = "none"
    tavily_api_key: str = ""
    serper_api_key: str = ""
    bing_api_key: str = ""

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    data_dir: Path = Path("./data")

    # --- Compliance ---
    user_agent: str = "CompetitiveAnalysisAgent/1.0"
    respect_robots: bool = True
    crawl_rate_limit_per_host: float = 1.0

    # --- Agent behavior ---
    max_qc_iterations: int = Field(default=2, ge=0, le=5)
    min_sources_per_competitor: int = Field(default=3, ge=1)

    @property
    def use_mock_llm(self) -> bool:
        """True when we should bypass the network and use canned LLM outputs."""
        return self.volc_mock or not self.ark_api_key or not self.ark_model_id

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "traces").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "reports").mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
