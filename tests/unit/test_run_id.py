"""generate_run_id() 的单元测试。

覆盖以下场景：
- 基本格式验证（UTC+8 日期时间格式）
- 无冲突时直接使用基础 ID
- 单次冲突时追加 _2 后缀
- 多次冲突后回退 UUID
- 时区正确性验证
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils.run_id import generate_run_id

# 匹配 YYYY-MM-DD_HH-mm-ss 格式的正则
_DATE_TIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")

# 匹配带序号的格式 YYYY-MM-DD_HH-mm-ss_N
_DATE_TIME_SEQ_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_\d+$")


class TestGenerateRunId:
    """测试 run_id 生成逻辑。"""

    def test_basic_format(self, tmp_path: Path) -> None:
        """验证生成的 run_id 符合 YYYY-MM-DD_HH-mm-ss 格式。"""
        run_id = generate_run_id(tmp_path)
        assert _DATE_TIME_PATTERN.match(run_id), (
            f"run_id '{run_id}' 不符合 YYYY-MM-DD_HH-mm-ss 格式"
        )

    def test_no_conflict_uses_base_id(self, tmp_path: Path) -> None:
        """验证无冲突时直接使用基础日期时间 ID。"""
        run_id = generate_run_id(tmp_path)

        # 目录不应提前存在
        assert not (tmp_path / run_id).exists()

        # 格式应为基础格式（无序号后缀）
        assert _DATE_TIME_PATTERN.match(run_id)

    def test_conflict_appends_sequence_number(self, tmp_path: Path) -> None:
        """验证目录已存在时追加 _2 序号。"""
        # 先生成一个 run_id 并创建对应目录
        first_id = generate_run_id(tmp_path)
        (tmp_path / first_id).mkdir(parents=True)

        # 使用固定时间确保生成相同的基础 ID
        from datetime import datetime
        from zoneinfo import ZoneInfo

        fixed_time = datetime.now(ZoneInfo("Asia/Shanghai"))
        base_id = fixed_time.strftime("%Y-%m-%d_%H-%M-%S")

        # 创建基础目录以模拟冲突
        (tmp_path / base_id).mkdir(parents=True, exist_ok=True)

        with patch("app.utils.run_id.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            second_id = generate_run_id(tmp_path)

        # 应追加 _2 后缀
        assert second_id == f"{base_id}_2"
        assert _DATE_TIME_SEQ_PATTERN.match(second_id)

    def test_multiple_conflicts_increment_sequence(self, tmp_path: Path) -> None:
        """验证多次冲突时序号递增。"""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        fixed_time = datetime.now(ZoneInfo("Asia/Shanghai"))
        base_id = fixed_time.strftime("%Y-%m-%d_%H-%M-%S")

        # 创建基础目录和 _2、_3 目录
        (tmp_path / base_id).mkdir(parents=True)
        (tmp_path / f"{base_id}_2").mkdir(parents=True)
        (tmp_path / f"{base_id}_3").mkdir(parents=True)

        with patch("app.utils.run_id.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            run_id = generate_run_id(tmp_path)

        assert run_id == f"{base_id}_4"

    def test_exceeds_max_retries_falls_back_to_uuid(self, tmp_path: Path) -> None:
        """验证超过最大冲突次数后回退使用 UUID。"""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        fixed_time = datetime.now(ZoneInfo("Asia/Shanghai"))
        base_id = fixed_time.strftime("%Y-%m-%d_%H-%M-%S")

        # 创建基础目录和 _2 到 _101 的所有目录
        (tmp_path / base_id).mkdir(parents=True)
        for i in range(2, 102):
            (tmp_path / f"{base_id}_{i}").mkdir(parents=True)

        with patch("app.utils.run_id.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            run_id = generate_run_id(tmp_path)

        # 应为 UUID 格式（32 位十六进制）
        assert len(run_id) == 32
        assert all(c in "0123456789abcdef" for c in run_id)

    def test_uses_utc_plus_8_timezone(self, tmp_path: Path) -> None:
        """验证使用 UTC+8 时区。"""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # 使用明确的 UTC+8 时间
        shanghai_now = datetime.now(ZoneInfo("Asia/Shanghai"))
        expected_prefix = shanghai_now.strftime("%Y-%m-%d_%H")

        run_id = generate_run_id(tmp_path, timezone="Asia/Shanghai")

        # run_id 应以当前 UTC+8 的日期和小时开头
        assert run_id.startswith(expected_prefix), (
            f"run_id '{run_id}' 不以 UTC+8 时间 '{expected_prefix}' 开头"
        )

    def test_custom_timezone(self, tmp_path: Path) -> None:
        """验证支持自定义时区。"""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        utc_now = datetime.now(ZoneInfo("UTC"))
        expected_prefix = utc_now.strftime("%Y-%m-%d_%H")

        run_id = generate_run_id(tmp_path, timezone="UTC")

        assert run_id.startswith(expected_prefix)

    def test_run_id_contains_only_safe_characters(self, tmp_path: Path) -> None:
        """验证 run_id 仅包含文件系统安全字符。"""
        run_id = generate_run_id(tmp_path)

        # 合法字符集：数字、字母、连字符、下划线
        assert re.match(r"^[a-zA-Z0-9_-]+$", run_id), (
            f"run_id '{run_id}' 包含不安全字符"
        )
