"""应用配置模块。

通过 pydantic-settings 从 .env 文件和环境变量中加载配置，
提供类型安全的配置访问方式，并使用 lru_cache 确保全局单例。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局应用配置。

    配置优先级：环境变量 > .env 文件 > 默认值。
    所有 LLM 相关配置项以 ``llm_`` 为前缀，与环境变量名自动映射。
    """

    # --- 应用基础信息 ---
    app_name: str = "autochecklist"
    app_version: str = "0.1.0"

    # --- 产物输出目录 ---
    output_dir: str = "output/runs"

    # --- LLM 连接配置 ---
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 60.0
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取全局配置单例。

    使用 ``lru_cache`` 保证整个应用生命周期内只实例化一次 Settings，
    避免重复读取 .env 文件带来的 IO 开销。
    """
    return Settings()
