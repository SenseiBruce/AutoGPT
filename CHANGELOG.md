# Changelog

All notable changes to this repository are documented in this file.

## Unreleased

### Added

- Root `docker-compose.yml` and `.devcontainer/` so a fresh clone can start the platform stack in isolation.
- `.env.example` files at the repo root and under `autogpt_platform/` listing the environment variables required to boot locally.
- Root `pytest` suite (`tests/`) and GitHub Actions `ci.yml` that run lint and tests on every push.
- Gitleaks secret scan workflow (`.github/workflows/secret-scan.yml`).
- Store full-text search query builder (`backend/server/v2/store/search.py`) with unit tests.
- Split oversized backend modules into focused files:
  - `blocks/llm_models.py`, `blocks/llm_call.py`, `blocks/llm_blocks.py`
  - `server/v2/store/db_agents.py`, `server/v2/store/db_submissions.py`
  - `blocks/google/gmail_models.py`, `blocks/google/gmail_mime.py`, `blocks/google/gmail_blocks.py`
- Frontend icons split into focused modules under `src/components/icons/`.

### Security

- Removed hardcoded Firebase web API credentials from `classic/frontend/lib/main.dart` in favor of compile-time environment variables.
- Documented that Postgres role passwords in `roles.sql` are injected from `POSTGRES_PASSWORD` at runtime and must be rotated if ever exposed.
