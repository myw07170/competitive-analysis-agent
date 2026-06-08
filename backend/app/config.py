"""从环境变量 / .env 文件加载的运行时配置。"""
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

    # --- LLM（火山方舟 Ark）---
    ark_api_key: str = ""
    ark_model_id: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_timeout: float = 60.0
    ark_max_retries: int = 2
    ark_use_json_mode: bool = False
    volc_mock: bool = False

    # --- 搜索后端 ---
    search_provider: Literal["tavily", "serper", "bing", "none"] = "none"
    tavily_api_key: str = ""
    serper_api_key: str = ""
    bing_api_key: str = ""

    # --- 服务器 ---
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    data_dir: Path = Path("./data")

    # --- 合规 ---
    user_agent: str = "CompetitiveAnalysisAgent/1.0"
    respect_robots: bool = True
    crawl_rate_limit_per_host: float = 1.0

    # --- 智能体行为 ---
    max_qc_iterations: int = Field(default=2, ge=0, le=5)
    min_sources_per_competitor: int = Field(default=3, ge=1)
    # 每竞品采集 / 分析的并行度（1 = 串行）。
    collector_concurrency: int = Field(default=3, ge=1, le=16)
    # 置信度感知的编排：其最佳来源低于此阈值的断言会被 QC 标记，
    # 并成为定向重新采集的候选项。
    min_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    # 自一致性：识别竞品时抽取多少个独立样本（做多数投票）。
    # 1 = 关闭（单样本）。
    self_consistency_samples: int = Field(default=1, ge=1, le=5)
    # 确定性的跨来源冲突检测（创新点 2）。
    enable_conflict_detection: bool = True

    @property
    def use_mock_llm(self) -> bool:
        """当应当绕过网络并使用预设 LLM 输出时返回 True。"""
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
