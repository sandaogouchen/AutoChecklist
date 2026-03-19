# app/utils/_ANALYSIS.md — 工具函数分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `app/utils/` |
| 文件数 | 3（含 `__init__.py`） |
| 分析文件 | 2 |
| 目录职责 | 底层工具函数：文件 I/O 辅助与运行 ID 生成 |
| 依赖层级 | 项目最底层模块，无内部依赖 |

## §2 文件清单

| # | 文件 | 类型 | 行数(估) | 核心导出 |
|---|------|------|----------|----------|
| 1 | `__init__.py` | - | 0 | 空 |
| 2 | `filesystem.py` | G-工具 | ~40 | `ensure_directory()`, `save_json()`, `load_json()`, `save_text()` |
| 3 | `run_id.py` | G-工具 | ~15 | `generate_run_id()` |

## §3 逐文件分析

### §3.1 filesystem.py

- **类型**: G-工具函数
- **职责**: 封装文件系统 I/O 操作，提供统一的 JSON/文本读写接口
- **函数清单**:
  | 函数 | 职责 | 参数 |
  |------|------|------|
  | `ensure_directory(path)` | 确保目录存在，不存在则递归创建 | Path |
  | `save_json(path, data)` | 将数据保存为 JSON 文件 | Path, Any |
  | `load_json(path)` | 从 JSON 文件加载数据 | Path → Any |
  | `save_text(path, content)` | 将文本保存到文件 | Path, str |
- **JSON 配置**: `ensure_ascii=False`（保留中文原文）, `indent=2`（可读性）
- **设计**: 纯函数，无状态，无副作用（除 I/O 本身）
- **调用方**: `RunRepository`, `RunStateRepository`, `PlatformDispatcher`

### §3.2 run_id.py

- **类型**: G-工具函数
- **职责**: 生成全局唯一的运行 ID
- **ID 格式**: `run_YYYYMMDD_HHMMSS_{4-char-uuid}`
  - 示例：`run_20260315_143052_a1b2`
  - 时间部分：UTC+8（北京时间）
  - 随机部分：UUID4 前 4 位十六进制字符
- **碰撞概率分析**:
  | 场景 | 同秒并发 | 碰撞概率 |
  |------|---------|----------|
  | 单用户 | 1 | ~0 |
  | 小团队 | 2-3 | ~1/65536 |
  | 高并发 | 10+ | 需考虑 |
- **时区选择**: 硬编码 UTC+8，适合中国团队使用场景。跨时区部署需注意 ID 的时间语义

## §4 补充观察

1. **依赖图底层**: `utils` 不依赖任何 `app.*` 模块，仅使用标准库（`pathlib`, `json`, `datetime`, `uuid`）。这是正确的依赖方向
2. **缺少原子写入**: `save_json()` 和 `save_text()` 使用标准 `open()` 写入，非原子操作。建议改用"写入临时文件 → `os.rename()`"模式
3. **缺少 `parse_run_id()`**: 有生成但无解析，无法从 ID 中提取时间信息。建议添加反向解析函数
4. **缺少 `get_data_dir()`**: 数据目录路径分散在各 repository 中硬编码。建议集中到 utils 或 settings
5. **可测试性**: 纯函数设计使单元测试简单直接，配合 `tmp_path` fixture 即可
