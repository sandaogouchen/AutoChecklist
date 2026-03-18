# app/utils/ 目录分析

> 生成时间: 2026-03-18 | 源文件数: 3 | 分析策略: Utility functions

## §1 目录职责

`app/utils/` 是 AutoChecklist 项目的**通用工具函数层**，为上层模块（仓储层、服务层）提供与业务无关的基础设施能力：

1. **文件系统操作** — `filesystem.py` 封装目录创建、JSON 读写、文本写入等常用文件操作，处理 Pydantic 模型的序列化适配。
2. **运行 ID 生成** — `run_id.py` 基于 UTC+8 时间戳生成人类可读的唯一运行标识，内置同名冲突检测与自动序号追加机制。

该目录遵循"零业务依赖"原则，不依赖任何 `app.domain`、`app.services` 等业务模块，仅依赖标准库和 Pydantic。

## §2 文件清单

| # | 文件名 | 行数 | 主要导出 | 职责概要 |
|---|--------|------|----------|----------|
| 1 | `__init__.py` | 1 | — | 包声明，标记 `utils` 为 Python 子包 |
| 2 | `filesystem.py` | 93 | `ensure_directory()`, `write_json()`, `read_json()`, `write_text()`, `_to_jsonable()` | 文件系统工具：目录创建、JSON/文本读写、Pydantic 序列化适配 |
| 3 | `run_id.py` | 65 | `generate_run_id()` | UTC+8 时间戳 run_id 生成（含冲突解决） |

## §3 文件详细分析

### §3.1 `__init__.py`

- **路径**: `app/utils/__init__.py`
- **行数**: 1
- **职责**: 包声明文件，仅含文档字符串 `"""通用工具函数子包。"""`。

#### §3.1.1 核心内容

空包初始化文件，无导出符号。

#### §3.1.2 依赖关系

无任何导入。

#### §3.1.3 关键逻辑 / 数据流

无逻辑，纯结构性文件。

---

### §3.2 `filesystem.py`

- **路径**: `app/utils/filesystem.py`
- **行数**: 93
- **职责**: 封装常用文件操作，为仓储层和其他需要文件 IO 的模块提供统一的基础设施。

#### §3.2.1 核心内容

**`ensure_directory(path: str | Path) -> Path`**:
- 确保目录存在，不存在则递归创建（`mkdir(parents=True, exist_ok=True)`）
- 返回 `Path` 对象
- 被所有需要创建目录的场景调用

**`write_json(path: str | Path, payload: Any) -> Path`**:
- 将任意数据序列化为格式化 JSON 并写入文件
- 自动调用 `_to_jsonable()` 处理 Pydantic 模型
- 自动调用 `ensure_directory()` 创建父目录
- 使用 `ensure_ascii=False` 保留中文字符，`indent=2` 格式化输出
- 编码固定为 UTF-8

**`read_json(path: str | Path) -> dict[str, Any]`**:
- 从文件读取并反序列化 JSON
- 不存在时抛 `FileNotFoundError`，内容非法时抛 `json.JSONDecodeError`
- 编码固定为 UTF-8

**`write_text(path: str | Path, content: str) -> Path`**:
- 纯文本写入，自动创建父目录
- 编码固定为 UTF-8

**`_to_jsonable(payload: Any) -> Any`** (内部函数):
- 递归将 payload 转换为 JSON 可序列化的原生类型
- 转换规则:
  - `BaseModel` → `model_dump(mode="json")`
  - `dict` → 递归处理每个值
  - `list` → 递归处理每个元素
  - 其他类型 → 原样返回

#### §3.2.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `json` (stdlib) | `json.dumps`, `json.loads` |
| `pathlib` (stdlib) | `Path` |
| `typing` (stdlib) | `Any` |
| `pydantic` | `BaseModel` |

唯一的第三方依赖是 `pydantic.BaseModel`（用于 `_to_jsonable()` 中的类型检查）。

#### §3.2.3 关键逻辑 / 数据流

```
write_json(path, payload)
  │
  ├── ensure_directory(path.parent)
  │     └── Path.mkdir(parents=True, exist_ok=True)
  │
  ├── _to_jsonable(payload) ←── 递归序列化适配
  │     ├── BaseModel → model_dump(mode="json")
  │     ├── dict → {k: _to_jsonable(v) for k, v in ...}
  │     ├── list → [_to_jsonable(item) for item in ...]
  │     └── other → 原样返回
  │
  └── Path.write_text(json.dumps(...), encoding="utf-8")

read_json(path)
  └── json.loads(Path.read_text(encoding="utf-8"))
```

**调用方分布**: `FileRunRepository` 使用 `write_json` / `read_json` / `write_text` / `ensure_directory`，`RunStateRepository` 使用 `write_json` / `read_json`。该模块是仓储层的核心基础设施。

---

### §3.3 `run_id.py`

- **路径**: `app/utils/run_id.py`
- **行数**: 65
- **职责**: 基于 UTC+8 日期时间生成人类可读的运行 ID，支持同名冲突检测与自动序号追加。

#### §3.3.1 核心内容

**常量**:
- `DEFAULT_TIMEZONE = "Asia/Shanghai"` — 默认 UTC+8 时区
- `_MAX_CONFLICT_RETRIES = 100` — 冲突序号上限

**`generate_run_id(output_dir: str | Path, timezone: str = DEFAULT_TIMEZONE) -> str`**:
- 格式: `YYYY-MM-DD_HH-mm-ss`（如 `2026-03-18_14-30-00`）
- 使用 `zoneinfo.ZoneInfo(timezone)` 获取时区感知的当前时间
- **冲突解决三级策略**:
  1. **首选**: 直接使用 `base_id`，检查 `output_dir / base_id` 目录不存在即返回
  2. **追加序号**: 从 `_2` 到 `_101`（100 次重试），格式为 `YYYY-MM-DD_HH-mm-ss_N`
  3. **UUID 回退**: 超过 100 次重试后使用 `uuid4().hex`，并 log warning

#### §3.3.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `datetime` (stdlib) | `datetime` |
| `pathlib` (stdlib) | `Path` |
| `uuid` (stdlib) | `uuid4` |
| `zoneinfo` (stdlib) | `ZoneInfo` |
| `logging` (stdlib) | `logging` |

纯标准库依赖，零第三方库。

#### §3.3.3 关键逻辑 / 数据流

```
generate_run_id(output_dir, timezone)
  │
  ├── datetime.now(ZoneInfo("Asia/Shanghai"))
  │     └── strftime("%Y-%m-%d_%H-%M-%S")  →  "2026-03-18_14-30-00"
  │
  ├── 检查: (output_dir / "2026-03-18_14-30-00").exists()?
  │     ├── 不存在 → 返回 "2026-03-18_14-30-00"
  │     └── 存在 → 进入冲突解决
  │
  ├── for seq in range(2, 102):
  │     candidate = "2026-03-18_14-30-00_{seq}"
  │     if not exists → 返回 candidate
  │
  └── 全部冲突 → uuid4().hex + logger.warning()
```

**设计特征**:
- **人类可读**: 时间戳格式直接可读，兼作运行目录名和 API 标识
- **时区固定**: 默认 UTC+8 (Asia/Shanghai)，通过参数可配置
- **乐观策略**: 绝大多数情况下首次检查即通过（秒级精度下冲突概率极低）
- **安全降级**: 极端情况下回退 UUID 确保唯一性

## §4 目录级依赖关系

### 内部依赖（utils 目录内）

`filesystem.py` 和 `run_id.py` 之间**无任何依赖**，完全独立。

### 外部依赖（依赖其他子包）

无。`app/utils/` 是整个项目中依赖最少的子包，仅依赖标准库和 `pydantic`。

```
filesystem.py ──→ pydantic.BaseModel（唯一第三方依赖）
run_id.py     ──→ 纯标准库
```

### 反向依赖（谁依赖 utils）

| 依赖方 | 使用的工具 |
|--------||-----------|
| `app.repositories.run_repository` | `ensure_directory`, `write_json`, `read_json`, `write_text` |
| `app.repositories.run_state_repository` | `write_json`, `read_json` |
| `app.services.workflow_service` | `generate_run_id` |

`app/utils/` 位于依赖图的最底层，是被依赖最广泛但自身无上游依赖的基础层。

## §5 设计模式与架构特征

1. **Infrastructure Layer（基础设施层）** — 该目录严格遵循分层架构的底层定位，不依赖任何业务模块，仅向上层提供通用能力。

2. **Adapter Pattern（适配器模式）** — `_to_jsonable()` 充当 Pydantic `BaseModel` 与标准库 `json.dumps()` 之间的适配器，递归处理嵌套的领域对象。

3. **Graceful Degradation（优雅降级）** — `generate_run_id()` 的三级冲突解决策略（直接 → 序号追加 → UUID 回退），确保在任何情况下都能生成唯一 ID。

4. **Convention-based Design（基于约定的设计）** — run_id 的格式 (`YYYY-MM-DD_HH-mm-ss`) 既是标识符又是目录名，通过约定将时间语义嵌入 ID 中，无需额外的元数据存储。

5. **Single Responsibility（单一职责）** — 每个文件职责单一：`filesystem.py` 只做文件 IO，`run_id.py` 只做 ID 生成。

## §6 潜在关注点

1. **`_to_jsonable()` 缺少对 `set`、`tuple`、`Enum` 等类型的处理** — 当前仅处理 `BaseModel`、`dict`、`list` 三种类型。如果 payload 中包含 `set`、`tuple`、`Enum`、`datetime` 等类型，`json.dumps()` 会抛出 `TypeError`。建议扩展覆盖范围或添加 `default` 参数。

2. **`read_json()` 返回类型固定为 `dict[str, Any]`** — 但 JSON 顶层也可以是列表（`list`）。例如 `checkpoints.json` 存储的是列表格式。类型注解与实际使用不完全匹配。

3. **`generate_run_id()` 的 TOCTOU 竞态** — 检查目录存在性和实际创建目录之间存在时间窗口。在高并发场景下，两个进程可能同时检测到同一 ID 不存在，然后都尝试创建。虽然目录创建本身使用 `exist_ok=True` 不会报错，但可能导致两个运行共享同一目录。

4. **`write_json()` 非原子写入** — 直接使用 `Path.write_text()` 写入，如果写入过程中进程崩溃，可能产生不完整的 JSON 文件。对于关键状态文件（如 `run_state.json`），建议采用"写入临时文件 + 原子重命名"模式。

5. **`generate_run_id()` 的秒级精度** — 格式为 `HH-mm-ss` 不包含毫秒。在快速连续创建运行时（如压力测试），同一秒内可能多次触发冲突解决逻辑。虽然有序号追加机制保底，但序号格式 `_2`, `_3` 不如直接使用毫秒精度优雅。

6. **`filesystem.py` 缺少文件删除工具** — 提供了创建和读写能力，但没有 `delete_file()` 或 `delete_directory()` 工具。如果未来需要清理过期运行目录，需要在仓储层自行实现删除逻辑。