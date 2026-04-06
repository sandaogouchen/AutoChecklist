# app/templates/ Directory Analysis

## §11.1 Directory Overview

The `templates/` directory at the repository root contains **a single YAML template file** used to define fixed checklist structures for specific product verticals. There is **no `app/templates/` directory** -- no Jinja2, HTML, or other rendering templates exist in the project. The application does not serve a web frontend; it is a FastAPI-based backend that outputs structured JSON and XMind files.

The template system in AutoChecklist refers to **checklist structure templates** (YAML-defined hierarchical node trees), not web page templates. These templates are loaded by `app/services/template_loader.py` and `app/nodes/template_loader.py` to provide a mandatory skeleton that the AI-generated checklist must conform to.

### Directory Contents

```
templates/
└── brand_spp_consideration.yaml    (1.5 KB)
```

**No `app/templates/` directory exists** -- confirmed by GitHub API search and local filesystem inspection.

---

## §11.2 File Analysis

### §11.2.1 `templates/brand_spp_consideration.yaml` (1,465 bytes)

**Purpose**: Defines a mandatory checklist skeleton for "brand S++ consideration" -- a fixed template for advertising campaign testing checklists.

**Structure**:

```yaml
metadata:
  name: "brand S++ consideration"
  version: "1.0.0"
  description: "brand S++ consideration 固定模版"
  mandatory_levels: [1, 2]          # Levels 1 and 2 are mandatory in output

nodes:                               # Hierarchical node tree
  - id: "doc"                        # Top-level: 文档信息 (Document Info)
    title: "文档信息"
    children:
      - id: "prd"                    # 需求文档 (Requirements Doc)
        children:
          - id: "prd-url"            # 需求文档链接
      - id: "FE-tech-design"         # 前端技术设计
      - id: "BE-tech-design"         # 后端技术设计
      - id: "test-plan"             # 测试方案

  - id: "create"                     # Top-level: 新建 (Create)
    title: "新建"
    children:
      - id: "campaign"              # campaign
        children:
          - id: "campaign-name"      # Campaign name (P2, mandatory)
            priority: "P2"
            mandatory: true
          - id: "campaign-objective"  # Campaign objective (P0)
            priority: "P0"
          - id: "campaign-budget"     # Campaign budget (P1)
            priority: "P1"
      - id: "adgroup"               # adgroup
        children:
          - id: "adgroup-targeting"   # Adgroup targeting (P1)
            priority: "P1"
          - id: "adgroup-bid"        # Adgroup bid (P0)
            priority: "P0"
      - id: "ad"                     # ad
        children:
          - id: "ad-creative"        # Ad creative (P1)
            priority: "P1"
          - id: "ad-landing-page"    # Ad landing page (P1)
            priority: "P1"
```

**Key Design Decisions**:

1. **`mandatory_levels: [1, 2]`** -- Controls which tree depths are considered mandatory in the output. The `MandatorySkeletonBuilder` service (`app/services/mandatory_skeleton_builder.py`) uses this to ensure that at least levels 1 and 2 of the template appear in the generated checklist, even if the AI does not generate matching checkpoints.

2. **Node IDs use kebab-case** (`campaign-name`, `adgroup-bid`) -- These IDs serve as stable anchors for merging template structure with AI-generated content. The checklist optimizer can map generated checkpoints to template nodes by matching semantic similarity.

3. **Priority annotations** (`P0`, `P1`, `P2`) on leaf nodes -- These propagate into the final checklist output and influence checkpoint prioritization. `P0` nodes (e.g., `campaign-objective`, `adgroup-bid`) represent critical test points.

4. **`mandatory: true` flag** -- Only appears on `campaign-name`, indicating it must appear in the output regardless of whether the AI generates a matching checkpoint. This is distinct from the level-based mandatory system.

5. **Domain-specific hierarchy** -- The template is structured around the advertising platform's CRUD operations: Document info -> Create -> Campaign/Adgroup/Ad. This maps directly to the testing workflow for TikTok/ByteDance advertising products.

**Consumers**:
- `app/services/template_loader.py` (9.6 KB) -- Parses the YAML, validates structure, builds the in-memory template tree
- `app/nodes/template_loader.py` (2.5 KB) -- LangGraph node wrapper that invokes the service and injects template context into the workflow state
- `app/services/mandatory_skeleton_builder.py` (4.7 KB) -- Extracts mandatory levels from the template and ensures they appear in the final output

---

## §11.3 Key Findings

1. **Single template, no template discovery mechanism.** The repository contains only one template (`brand_spp_consideration.yaml`). The `template_loader.py` service likely accepts a template path as input, but there is no template registry, no template listing API, and no template selection logic visible in the codebase. Adding a new template requires creating a new YAML file and passing its path to the workflow.

2. **No test coverage for template loading.** Neither `app/services/template_loader.py` nor `app/nodes/template_loader.py` has a dedicated test file. The template YAML format is not validated by any test. A malformed template (missing `metadata`, invalid `mandatory_levels`, circular node references) would not be caught until runtime.

3. **The `mandatory_levels` mechanism is a key architectural feature** that ensures the AI-generated checklist preserves the organizational structure expected by QA teams. Without it, the AI might flatten or reorganize the hierarchy in unexpected ways.

4. **Template format is ad-hoc YAML** -- There is no JSON Schema, Pydantic model validation, or formal specification for the template format. The `template_models.py` domain file likely defines the Pydantic models, but there are no tests verifying round-trip YAML-to-model-to-tree conversion.

5. **No `app/templates/` directory exists** because AutoChecklist is a pure API backend. The "templates" concept in this project refers exclusively to checklist structure templates (YAML data files), not web rendering templates. The UI is expected to be a separate frontend application consuming the API.

---

## §11.4 Cross-References

- **Template loading pipeline**: `templates/*.yaml` -> `app/services/template_loader.py` -> `app/nodes/template_loader.py` -> workflow state `template_context`
- **Mandatory skeleton**: `templates/*.yaml` (metadata.mandatory_levels) -> `app/services/mandatory_skeleton_builder.py` -> merged into `optimized_tree`
- **Domain models**: `app/domain/template_models.py` defines the Pydantic models for template structure
- **Testing gap**: No test file covers template loading -- see `analysis_output/tests/_ANALYSIS.md` (§14.2.3, item 6) for recommendation
- **Checklist optimizer relationship**: The template provides the structural backbone that `ChecklistMerger` and `structure_assembler_node` must respect when organizing AI-generated checkpoints
- **Single template limitation**: Only `brand_spp_consideration.yaml` exists; the system's ability to handle diverse template types (e.g., different product verticals, different mandatory_levels configurations) is unverified
