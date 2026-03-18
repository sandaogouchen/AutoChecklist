"""运行 ID 生成工具。

封装基于 UTC+8 日期时间的 run_id 生成逻辑，
支持同名冲突检测与自动序号追加。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# 默认时区：UTC+8（Asia/Shanghai）
DEFAULT_TIMEZONE = "Asia/Shanghai"

# 冲突序号上限，超过后回退使用 UUID
_MAX_CONFLICT_RETRIES = 100


def generate_run_id(
    output_dir: str | Path,
    timezone: str = DEFAULT_TIMEZONE,
) -> str:
    """生成基于 UTC+8 日期时间的运行 ID。

    格式为 ``YYYY-MM-DD_HH-mm-ss``，同时用作运行目录名称和 API 标识。
    当目标目录已存在时，自动追加递增序号（``_2``、``_3`` ...），
    最多尝试 100 次，超过后回退使用 UUID。

    Args:
        output_dir: 运行结果的根目录（如 ``output/runs``）。
        timezone: IANA 时区名称，默认 ``Asia/Shanghai``。

    Returns:
        唯一的 run_id 字符串。
    """
    root = Path(output_dir)

    # 获取 UTC+8 当前时间并格式化
    now = datetime.now(ZoneInfo(timezone))
    base_id = now.strftime("%Y-%m-%d_%H-%M-%S")

    # 首选：直接使用基础 ID
    candidate = base_id
    if not (root / candidate).exists():
        return candidate

    # 冲突时追加递增序号
    for seq in range(2, _MAX_CONFLICT_RETRIES + 2):
        candidate = f"{base_id}_{seq}"
        if not (root / candidate).exists():
            return candidate

    # 极端情况：序号用尽，回退 UUID
    fallback = uuid4().hex
    logger.warning(
        "run_id 冲突序号超过 %d 次上限，回退使用 UUID: %s",
        _MAX_CONFLICT_RETRIES,
        fallback,
    )
    return fallback
