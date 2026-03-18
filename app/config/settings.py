"""应用配置模块。

通过 pydantic-settings 从 .env 文件和环境变量中加载配置。
新增迭代评估回路相关配置项。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局应用配置。"""

    app_name: str = "autochecklist"
    app_version: str = "0.1.0"
    output_dir: str = "output/runs"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 6000.0
    llm_temperature: float = 0.2
    llm_max_tokens: int = 16000

    # ---- 迭代评估回路配置 ----
    max_iterations: int = 3
    evaluation_pass_threshold: float = 0.7

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
