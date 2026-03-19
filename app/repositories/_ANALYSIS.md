# app/repositories/_ANALYSIS.md — 数据持久化层分析

> 分析分支自动生成 · 源分支 `main`

---

## §1 目录概述

| 维度 | 值 |
|------|-----|
| 路径 | `app/repositories/` |
| 文件数 | 4（含 `__init__.py`） |
| 分析文件 | 3 |
| 目录职责 | 数据持久化层：混合存储策略（SQLite 结构化数据 + 文件系统 JSON） |

## §2 文件清单

| # | 文件 | 类型 | 存储后端 | 概要 |
|---|------|------|----------|------|
| 1 | `__init__.py` | - | - | 空 |
| 2 | `project_repository.py` | F-数据访问 | SQLite | 项目上下文 CRUD |
| 3 | `run_repository.py` | F-数据访问 | 文件系统 | 运行结果存储 |
| 4 | `run_state_repository.py` | F-数据访问 | 文件系统 | 迭代状态存储 |

## §3 逐文件分析

### §3.1 project_repository.py

- **类型**: F-数据访问
- **存储**: SQLite 数据库 `data/projects.db`
- **核心类**: `ProjectRepository`
- **CRUD 操作**: `list_all()`, `create()`, `get_by_id()`, `update()`, `delete()`
- **建表策略**: 首次实例化时自动创建表（`CREATE TABLE IF NOT EXISTS`）
- **序列化处理**: list 类型字段使用 `json.dumps()`/`json.loads()` 存储为 JSON 字符串
- **ID 生成**: UUID4 字符串
- **并发考虑**: SQLite 的写锁可能在多用户并发场景下成为瓶颈

### §3.2 run_repository.py

- **类型**: F-数据访问
- **存储**: 文件系统 `data/{run_id}/result.json`
- **核心类**: `RunRepository`
- **操作**: `save(run_id, result)` 保存结果, `load(run_id)` 加载结果
- **文件系统选择原因**:
  - 运行结果数据量大（含完整测试用例集、markdown 渲染结果）
  - 文件形式便于人工调试和检查
  - 每次运行天然隔离在独立目录
- **数据格式**: Pydantic model → `.model_dump()` → JSON

### §3.3 run_state_repository.py

- **类型**: F-数据访问
- **存储**: 文件系统 `data/{run_id}/state.json`
- **核心类**: `RunStateRepository`
- **职责**: 保存/加载 `RunState`（包含 `IterationRecord` 列表）
- **与 `RunRepository` 的职责边界**:
  | Repository | 存储内容 | 写入时机 | 读取场景 |
  |-----------|---------|---------|----------|
  | RunRepository | 最终结果 | 工作流完成后 | API 查询 |
  | RunStateRepository | 迭代过程 | 每轮迭代后 | 断点恢复/调试 |

## §4 补充观察

1. **混合存储策略合理**: 结构化元数据（项目配置）使用 SQLite 提供 CRUD 便利性；大体量运行数据使用文件系统提供隔离性和可调试性
2. **缺乏数据清理机制**: `data/{run_id}/` 目录会随运行次数持续增长，无 TTL（Time-To-Live）或自动清理策略。建议添加定期清理 CLI 命令或配置最大保留天数
3. **原子性风险**: 文件写入使用标准 `open()` + `json.dump()`，非原子操作。进程在写入过程中被终止可能产生损坏的 JSON 文件。建议引入"写临时文件 → rename"的原子写入模式
4. **SQLite 并发**: 单文件 SQLite 在写并发场景下使用全局写锁，多用户同时创建/修改项目可能出现锁等待。当前作为单用户/低并发 MVP 可接受
5. **缺少 Repository 抽象**: 三个 repository 类无统一接口/基类，如未来需要替换存储后端（如 PostgreSQL），需逐个修改。建议引入 `Repository` Protocol
