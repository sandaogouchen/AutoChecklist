# app/repositories/ 目录分析

> 生成时间: 2026-03-18 | 源文件数: 4 | 分析策略: Business logic + persistence patterns

## §1 目录职责

`app/repositories/` 是 AutoChecklist 项目的**数据持久化层**，实现 Repository 模式以隔离业务逻辑与存储细节。该目录包含两种截然不同的持久化策略：

1. **内存存储** — `ProjectRepository` 使用 `dict` 作为 MVP 阶段的项目上下文存储，接口预留了面向数据库迁移的设计。
2. **文件系统存储** — `FileRunRepository` 和 `RunStateRepository` 将运行产物和迭代状态持久化为 JSON/文本文件，采用 `output/runs/<run_id>/` 的目录隔离结构。

三个仓储协同工作：`ProjectRepository` 管理项目元数据，`FileRunRepository` 管理运行产物，`RunStateRepository` 管理迭代状态。后两者共享相同的目录结构，通过 `run_id` 建立关联。

## §2 文件清单

| # | 文件名 | 行数 | 主要导出 | 职责概要 |
|---|--------|------|----------|----------|
| 1 | `__init__.py` | 1 | — | 包声明，标记 `repositories` 为 Python 子包 |
| 2 | `project_repository.py` | 37 | `ProjectRepository` | 项目上下文的内存字典存储 |
| 3 | `run_repository.py` | 70 | `FileRunRepository` | 基于文件系统的运行产物仓储（JSON + 文本） |
| 4 | `run_state_repository.py` | 110 | `RunStateRepository` | 运行状态/评估报告/迭代日志的文件持久化 |

## §3 文件详细分析

### §3.1 `__init__.py`

- **路径**: `app/repositories/__init__.py`
- **行数**: 1
- **职责**: 包声明文件，仅含文档字符串 `"""运行记录持久化子包。"""`。

#### §3.1.1 核心内容

空包初始化文件，无导出符号。

#### §3.1.2 依赖关系

无任何导入。

#### §3.1.3 关键逻辑 / 数据流

无逻辑，纯结构性文件。

---

### §3.2 `project_repository.py`

- **路径**: `app/repositories/project_repository.py`
- **行数**: 37
- **职责**: 项目上下文的薄持久化层，MVP 阶段使用内存字典实现，接口窄化以便未来替换为数据库实现。

#### §3.2.1 核心内容

**类 `ProjectRepository`**:
- 内部存储: `_store: dict[str, ProjectContext]`，以 `ProjectContext.id` 为键
- **写入方法**:
  - `save(project)` → 插入或更新（upsert 语义），返回传入对象
  - `delete(project_id)` → 删除并返回布尔值（使用 `dict.pop(key, None)`）
- **读取方法**:
  - `get(project_id)` → 按 ID 查找，不存在返回 `None`
  - `list_all()` → 返回所有值的列表副本

#### §3.2.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `app.domain.project_models` | `ProjectContext` |
| `typing` (stdlib) | `Optional` |

零外部依赖，仅依赖领域模型。

#### §3.2.3 关键逻辑 / 数据流

```
ProjectContextService
       │
       ▼
ProjectRepository._store (dict)
       │
  save()  → _store[project.id] = project
  get()   → _store.get(project_id)
  delete()→ _store.pop(project_id, None)
  list()  → list(_store.values())
```

**设计特征**:
- **纯内存**: 进程重启后数据丢失，适合 MVP/测试场景
- **窄接口**: 只有 4 个方法（save/delete/get/list_all），面向接口替换设计
- **Upsert 语义**: `save()` 不区分新建和更新，直接覆写
- **无线程安全**: 无锁机制，多线程访问可能出现竞态条件

---

### §3.3 `run_repository.py`

- **路径**: `app/repositories/run_repository.py`
- **行数**: 70
- **职责**: 基于文件系统的运行记录仓储，每个 `run_id` 对应一个独立子目录，存储该次运行的所有产物文件。

#### §3.3.1 核心内容

**类 `FileRunRepository`**:
- 构造参数: `root_dir: str | Path` — 运行结果的根目录
- **写入方法**:
  - `save(run_id, payload, filename="run_result.json")` → 将 dict 序列化为 JSON 写入 `{root_dir}/{run_id}/{filename}`
  - `save_text(run_id, filename, content)` → 将纯文本写入指定文件
- **读取方法**:
  - `load(run_id, filename="run_result.json")` → 反序列化 JSON 文件，不存在时抛 `FileNotFoundError`
  - `artifact_path(run_id, filename)` → 获取产物文件路径（不检查存在性）
- **内部方法**:
  - `_run_dir(run_id)` → 返回 `ensure_directory(root_dir / run_id)`，自动创建目录

#### §3.3.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `app.utils.filesystem` | `ensure_directory`, `read_json`, `write_json`, `write_text` |
| `pathlib` (stdlib) | `Path` |
| `typing` (stdlib) | `Any` |

完全委托 `app.utils.filesystem` 处理底层文件 IO。

#### §3.3.3 关键逻辑 / 数据流

```
output/runs/                          ← root_dir
  └── 2026-03-18_14-30-00/            ← run_id 目录
        ├── request.json              ← WorkflowService 保存
        ├── run_result.json           ← 最终运行结果
        ├── parsed_document.json      ← PlatformDispatcher 保存
        ├── research_output.json
        ├── checkpoints.json
        ├── checkpoint_coverage.json
        ├── test_cases.json
        ├── test_cases.md
        ├── quality_report.json
        └── checklist.xmind           ← 可选 XMind 产物
```

**调用链**: `WorkflowService` / `PlatformDispatcher` → `FileRunRepository.save()` / `save_text()` → `app.utils.filesystem.write_json()` / `write_text()` → 物理文件

---

### §3.4 `run_state_repository.py`

- **路径**: `app/repositories/run_state_repository.py`
- **行数**: 110
- **职责**: 运行状态的文件持久化仓储，负责 `run_state.json`、`evaluation_report.json`、`iteration_log.json` 三类状态文件的读写。

#### §3.4.1 核心内容

**类 `RunStateRepository`**:
- 构造参数: `root_dir: str | Path` — 与 `FileRunRepository` 共享相同根目录

**运行状态 (run_state.json)**:
- `save_run_state(run_state: RunState)` → 序列化完整运行状态
- `load_run_state(run_id)` → 反序列化为 `RunState` 对象
- `run_state_exists(run_id)` → 检查文件是否存在

**评估报告 (evaluation_report.json)**:
- `save_evaluation_report(run_id, report, iteration_index)`:
  - 始终覆写 `evaluation_report.json`（当前版本）
  - 当 `iteration_index > 0` 时额外保存 `evaluation_report_iter_{N}.json`（历史版本）
- `load_evaluation_report(run_id)` → 加载当前版本

**迭代日志 (iteration_log.json)**:
- `save_iteration_log(run_state)` → 从 `RunState` 提取迭代历史和回流决策，组装为结构化日志
- `load_iteration_log(run_id)` → 加载日志

**内部方法**:
- `_save(run_id, payload, filename)` → 通用 JSON 保存
- `_load(run_id, filename)` → 通用 JSON 加载
- `_run_dir(run_id)` → 获取运行目录（自动创建）

#### §3.4.2 依赖关系

| 依赖目标 | 导入内容 |
|----------|----------|
| `app.domain.run_state` | `EvaluationReport`, `RunState` |
| `app.utils.filesystem` | `read_json`, `write_json` |
| `pathlib` (stdlib) | `Path` |
| `typing` (stdlib) | `Any` |

#### §3.4.3 关键逻辑 / 数据流

```
output/runs/{run_id}/
  ├── run_state.json                 ← save_run_state() / load_run_state()
  │     {run_id, status, current_stage, iteration_index,
  │      iteration_history[], retry_decisions[], timestamps{}}
  │
  ├── evaluation_report.json         ← save_evaluation_report() (当前版本，覆写)
  │     {overall_score, dimensions[], improvement_summary}
  │
  ├── evaluation_report_iter_1.json  ← save_evaluation_report(iteration_index=1)
  ├── evaluation_report_iter_2.json  ← (历史版本，追加)
  │
  └── iteration_log.json             ← save_iteration_log()
        {run_id, total_iterations, final_status,
         iterations[], retry_decisions[]}
```

**评估报告版本管理策略**:
- `evaluation_report.json` 始终指向**最新一轮**评估结果（覆写语义）
- `evaluation_report_iter_{N}.json` 保留**历史版本**（仅在 `iteration_index > 0` 时生成）
- 首轮（`iteration_index=0`）不生成历史版本文件

**迭代日志结构**: `save_iteration_log()` 将 `RunState` 中的 `iteration_history` 和 `retry_decisions` 两个列表提取出来，组装为独立的结构化日志文件，便于外部分析和审计。

## §4 目录级依赖关系

### 内部依赖（repositories 目录内）

三个仓储类之间**无直接依赖**，彼此独立。它们通过共享 `run_id` 和相同的 `root_dir` 建立隐式关联。

### 外部依赖（依赖其他子包）

```
project_repository.py ──→ app.domain.project_models (ProjectContext)

run_repository.py ────────→ app.utils.filesystem (ensure_directory, read_json,
                                                   write_json, write_text)

run_state_repository.py ──┬→ app.domain.run_state (EvaluationReport, RunState)
                          └→ app.utils.filesystem (read_json, write_json)
```

### 反向依赖（谁依赖 repositories）

| 依赖方 | 使用的仓储 |
|--------|-----------|
| `app.services.project_context_service` | `ProjectRepository` |
| `app.services.workflow_service` | `FileRunRepository`, `RunStateRepository` |
| `app.services.platform_dispatcher` | `FileRunRepository` (TYPE_CHECKING) |

## §5 设计模式与架构特征

1. **Repository Pattern（仓储模式）** — 三个类均实现仓储模式，将数据访问逻辑封装在统一接口后面。`ProjectRepository` 提供内存实现（面向替换），`FileRunRepository` 和 `RunStateRepository` 提供文件系统实现。

2. **Convention-over-Configuration（约定优于配置）** — 目录结构 `{root_dir}/{run_id}/{filename}` 是隐式约定，`FileRunRepository` 和 `RunStateRepository` 共享此约定但不通过代码显式耦合。

3. **Separation of Concerns（关注点分离）** — 运行产物（`FileRunRepository`）和运行状态（`RunStateRepository`）被分为两个独立仓储，各自管理不同类型的持久化数据。

4. **Thin Delegation（薄委托）** — `FileRunRepository` 和 `RunStateRepository` 将底层文件 IO 完全委托给 `app.utils.filesystem`，自身仅负责路径组装和领域对象的序列化/反序列化。

5. **Narrow Interface（窄接口）** — `ProjectRepository` 仅暴露 4 个方法（save/delete/get/list_all），有意限制接口宽度以便未来替换实现。

6. **Versioned Artifacts（版本化产物）** — `RunStateRepository` 的评估报告采用"覆写当前版本 + 追加历史版本"的双轨策略。

## §6 潜在关注点

1. **`ProjectRepository` 内存存储的局限性** — 纯内存字典意味着进程重启后数据丢失。虽然 docstring 说明了这是 MVP 设计，但如果项目上下文需要在多次运行间持久化，需要迁移到文件或数据库存储。

2. **`FileRunRepository._run_dir()` 被外部直接访问** — `PlatformDispatcher` 中调用 `self.repository._run_dir(run_id)` 直接访问以 `_` 开头的私有方法，破坏了封装性。建议将 `_run_dir()` 提升为公开方法或提供 `get_run_dir(run_id)` 公开接口。

3. **`RunStateRepository._run_dir()` 与 `FileRunRepository._run_dir()` 的语义差异** — 两者都创建 `root_dir / run_id` 目录，但 `FileRunRepository` 使用 `ensure_directory()` 工具函数，`RunStateRepository` 使用 `Path.mkdir(parents=True, exist_ok=True)` 直接调用。建议统一实现。

4. **无并发保护** — `ProjectRepository` 的内存字典和文件系统仓储的 JSON 读写都没有锁机制。多进程/多线程同时写入同一 `run_id` 目录可能导致文件损坏。

5. **`save_evaluation_report` 的首轮不保存历史版本** — 当 `iteration_index=0` 时仅覆写 `evaluation_report.json` 而不创建 `evaluation_report_iter_0.json`。这意味着如果有后续迭代，首轮的评估报告会被覆写而无法独立恢复（除非从 `iteration_log.json` 中间接获取分数）。

6. **load 方法缺乏统一的 Not Found 处理** — `FileRunRepository.load()` 依赖 `read_json()` 抛出 `FileNotFoundError`，而 `RunStateRepository` 提供了 `run_state_exists()` 预检方法。两个仓储的错误处理策略不一致。