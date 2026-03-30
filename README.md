# Autonomous Dev Pipeline (V1)

A fully local, deterministic software delivery pipeline for existing Git repositories.

This project runs a bounded agent graph that can:

1. Normalize a requirement into a machine-readable task spec.
2. Inspect an existing repository and infer likely quality commands.
3. Plan implementation steps and completion criteria.
4. Create a feature branch in an isolated workspace clone.
5. Apply code edits via constrained tool wrappers.
6. Run tests/lint/typecheck/build through an allowlisted command runner.
7. Perform structured self-review on the diff.
8. Loop through fixes until gates pass or hard limits are hit.
9. Produce branch, commit(s), PR draft payload, evidence, and risk summary for human review.

It targets local/offline model hosting via an OpenAI-compatible endpoint (for example llama.cpp serving Qwen3).

## Architecture

The runtime uses a deterministic LangGraph state machine:

`INTAKE -> INSPECT -> PLAN -> IMPLEMENT -> VERIFY -> REVIEW -> FIX_OR_PR -> DONE`

Roles are implemented as constrained nodes, not unrestricted shell agents:

- Intake agent: validates and normalizes input.
- Planner agent: creates structured plan and test strategy.
- Implementer agent: proposes scoped file edits.
- Reviewer agent: reviews diff and emits structured findings.
- Fixer agent: patches based on failing checks/findings.
- PR writer agent: generates title/body/checklist and risk narrative.

Core subsystems:

- `app/orchestration/`: graph wiring and node logic
- `app/tools/`: file/git/command/repo-inspection/github/artifact wrappers
- `app/storage/`: SQLite run metadata persistence
- `app/runtime/`: workspace isolation and safety limits
- `app/llm/`: thin OpenAI-compatible chat client with schema validation

## Safety and guardrails

- All file I/O is workspace-root constrained.
- Command execution is allowlist-only.
- No force-push.
- No merge to `main`/`master`.
- Bounded iteration and fix loops.
- Hard change limits (file count, line delta, tool calls).
- Dry-run mode supported.
- Human final review is mandatory by design.

## Setup

### Prerequisites

- Python 3.11+
- Git CLI
- Optional: GitHub CLI (`gh`) for PR creation
- Optional: Docker (sandbox toggle is configurable; local execution is default in V1)

### Install

```bash
python -m venv .venv
. .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Configuration

Copy `config/settings.example.yaml` and adjust values.

Important model fields (defaulted for your provided endpoint):

- `model.base_url: http://10.0.0.113/v1`
- `model.model_name: qwen3`
- `model.api_key: EMPTY` (placeholder; can be blank for many local servers)

Also configure:

- `workspace.root`
- max loops/limits
- command allowlist
- default verification commands
- GitHub PR integration toggle
- optional Docker sandbox toggle

## Running locally

### CLI run

```bash
python -m app.cli run \
  --repo /path/to/repo-or-git-url \
  --requirement-file app/examples/sample_requirement.md \
  --base-branch main \
  --config config/settings.example.yaml
```

Optional flags:

- `--dry-run`
- `--no-pr`
- `--max-iterations 5`
- `--test-command "pytest -q"`
- `--lint-command "ruff check ."`
- `--build-command "npm run build"`

### API run

```bash
uvicorn app.api:create_app --factory --host 0.0.0.0 --port 8000
```

Endpoints:

- `POST /runs`
- `GET /runs/{run_id}`
- `GET /health`

## llama.cpp OpenAI-compatible endpoint

This project uses `httpx` directly against the OpenAI-compatible Chat Completions API.

Set in config/env:

- `model.base_url` to your llama.cpp endpoint (`.../v1`)
- `model.model_name` to your served model (`qwen3`)
- `model.api_key` placeholder if your gateway requires it

## Repo input modes

- Local path: workspace clone is created with `git clone <local-path> <workspace-run>/repo`
- Remote git URL: workspace clone is created with `git clone <url> <workspace-run>/repo`

The source repository is never edited directly.

## PR creation behavior

- If `github.enabled=true` and `gh` is authenticated, pipeline can call `gh pr create`.
- Otherwise it emits:
  - exact `gh` command
  - markdown PR body artifact
  - branch/commit details for manual submission

## Testing

```bash
pytest
```

Tests cover config loading, schema validation, repo inspection, graph smoke flow, command allowlist, git tool behavior, and PR payload generation.

## V1 tradeoffs

- Implementation edits rely on model-generated full-file rewrites for scoped files; this is simple and debuggable but not optimal for very large files.
- Docker sandbox support is config-wired, but local host execution is the primary V1 path.
- Resume support replays graph with persisted state and stage-skips, not arbitrary mid-node continuation.
- Reviewer and fixer are strong structured helpers, but final human review remains required.

## How to evolve this to a larger agent swarm

1. Keep this deterministic graph as control-plane and add sidecar workers per stage.
2. Split planning into architecture/test/security reviewers in parallel with mergeable schemas.
3. Replace single implementer with scoped module workers owning disjoint file sets.
4. Add retrieval/index service for large monorepos.
5. Introduce optional LiteLLM router for multi-model policy and fallback while keeping direct local endpoint support.

## Stubbed or partial in V1

- Docker sandboxing: wired in config and command path, but host execution is still the primary mode.
- Mid-node resume: run resume support replays from the last completed stage, not from arbitrary in-node checkpoints.
- Diff-aware patching: implementer/fixer currently apply model-proposed full-file content for scoped files; a token-level patch planner is a next-step upgrade.

## Out of scope for V1

- Autonomous merge to protected branches.
- Distributed execution infrastructure.
- Fully semantic refactor engine across very large repos.
- Multi-tenant SaaS control plane.
