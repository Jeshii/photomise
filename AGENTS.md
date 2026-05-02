# AGENTS.md

## Database
- Uses TinyDB (JSON file-based, `tinydb==4.8.2`)
- `SharedDB` (global): Stores projects, locations, filters. Path: `shared.json` (relative, per `photomise/utilities/constants.py:3`)
- `ProjectDB` (per-project): Stores events, photos, posts, rankings. Path: `{project_path}/db/project.json` (created on `photomise init`)

## Tech Stack
- Python 3.12+ (ruff target-version in `pyproject.toml`)
- Typer CLI, entry point: `photomise.cli.main:app`
- Editable install: `pip install -r requirements.txt` (includes `-e .`)

## Conventions
- Per-project settings (event radius, time delta) live in project DB, not shared DB, for portability
- `photomise init` creates `{project_path}/db` and `{project_path}/assets` directories
- Linting: Ruff only, config in `pyproject.toml`. No tests or CI workflows exist currently
