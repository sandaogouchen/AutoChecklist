"""应用配置模块。

通过 pydantic-settings 从 .env 文件和环境变量中加载配置。
新增 enable_checklist_optimization 配置项。
新增模版相关配置项。
新增 knowledge_* 系列配置项，支持 GraphRAG 知识检索功能。
新增 llm_max_retries / llm_retry_* / llm_fallback_* 系列配置项，
支持 LLM 调用重试与模型降级。
新增 CocoSettings，支持 Coco Agent 代码搜索配置。
新增 checkpoint_batch_* 配置项，支持 Checkpoint 分批规划。
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
    llm_max_tokens: int = 50000

    # ---- LLM 重试与降级配置 ----
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0
    llm_retry_max_delay: float = 60.0
    llm_fallback_model: str = ""
    llm_fallback_base_url: str = ""
    llm_fallback_api_key: str = ""

    # ---- 迭代评估回路配置 ----
    max_iterations: int = 3
    evaluation_pass_threshold: float = 0.7

    # ---- Checklist 优化配置 ----
    enable_checklist_optimization: bool = True

    # ---- Checkpoint 分批规划配置 ----
    checkpoint_batch_threshold: int = 20
    checkpoint_batch_size: int = 20

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


class CocoSettings(BaseSettings):
    """Coco Agent 代码搜索配置。

    用于连接 ByteDance Coco Agent API，支持代码库语义搜索、
    函数定义查找、AST 分析等功能。
    """

    coco_api_base_url: str = "https://coco.bytedance.net/api/v1"
    coco_jwt_token: str = ""
    coco_agent_name: str = "autochecklist"
    coco_task_timeout: int = 120
    coco_poll_interval_start: float = 2.0
    coco_poll_interval_max: float = 10.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def get_coco_settings() -> CocoSettings:
    return CocoSettings()
