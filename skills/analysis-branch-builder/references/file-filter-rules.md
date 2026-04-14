# File Filter Rules

Apply these rules before deciding which files or directories receive analysis.

## Always Skip

| Category | Rules |
| --- | --- |
| Lock files | `uv.lock`, `package-lock.json`, `yarn.lock`, `poetry.lock`, `Cargo.lock`, `go.sum`, `pnpm-lock.yaml` |
| Generated directories | `node_modules/`, `__pycache__/`, `.git/`, `dist/`, `build/`, `.next/`, `target/`, `venv/`, `.venv/`, `*.egg-info/` |
| Binary or media | `.png`, `.jpg`, `.jpeg`, `.gif`, `.ico`, `.svg`, `.woff`, `.woff2`, `.ttf`, `.eot`, `.pdf`, `.zip`, `.tar.gz`, `.mp4`, `.mp3` |
| Secrets | `.env` and any file that contains real secret values |
| IDE and cache | `.idea/`, `.cache/`, `.tmp/`, `*.pyc`, `*.pyo`, `.DS_Store`, `Thumbs.db` |

## Keep as Exceptions

- Keep `.env.example`.
- Keep `.vscode/settings.json` and `.vscode/launch.json` if present.
- Keep text docs such as `README.md`, `CONTRIBUTING.md`, and `docs/**/*.md`.

## Directory Attribution Rules

- Root files belong in `_ROOT_ANALYSIS.md`.
- A directory gets `_ANALYSIS.md` only if it has source or config files directly inside it.
- A directory with only subdirectories does not get its own `_ANALYSIS.md`.
- If a directory has more than 20 direct files, split into `_ANALYSIS_1.md`, `_ANALYSIS_2.md`, and so on, with at most 15 files per analysis file.
- If nesting exceeds 5 levels, fold the deepest files into the nearest supported parent analysis file and note the fallback.

## Scan Depth

- Default to a maximum scan depth of 5.
- If the repo has deeper paths that clearly matter, record the fallback instead of inventing a sixth-level mirror rule.
