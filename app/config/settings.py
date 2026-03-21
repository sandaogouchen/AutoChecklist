"""应用配置模块。

通过 pydantic-settings 从 .env 文件和环境变量中加载配置。
新增 enable_checklist_optimization 配置项。
新增模版相关配置项。
新增 knowledge_* 系列配置项，支持 GraphRAG 知识检索功能。
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

    # ---- Checklist 优化配置 ----
    enable_checklist_optimization: bool = True

    # ---- 模版配置 ----
    template_dir: str = "templates"
    enable_mandatory_source_labels: bool = True

    # ---- 时区配置 ----
    timezone: str = "Asia/Shanghai"

    # ---- 知识检索配置（GraphRAG / LightRAG） ----
    enable_knowledge_retrieval: bool = False
    knowledge_working_dir: str = "./knowledge_db"
    knowledge_docs_dir: str = "./knowledge_docs"
    knowledge_retrieval_mode: str = "hybrid"
    knowledge_top_k: int = 10
    knowledge_embedding_model: str = ""
    knowledge_max_doc_size_kb: int = 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
