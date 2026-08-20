# Changelog

All notable changes to this repository are documented in this file.

## Unreleased

### Added

- Root `docker-compose.yml` and `.devcontainer/` so a fresh clone can start the platform stack in isolation.
- `.env.example` files at the repo root and under `autogpt_platform/` listing the environment variables required to boot locally.
- Root `pytest` suite (`tests/`) and GitHub Actions `ci.yml` that run lint and tests on every push.
- Gitleaks secret scan workflow (`.github/workflows/secret-scan.yml`).
- Store full-text search query builder (`backend/server/v2/store/search.py`) with unit tests.
- Split oversized backend modules into focused files under 1000 LOC:
  - LLM: `llm_models.py`, `llm_call.py`, `llm_base.py`, `llm_structured.py`, `llm_text_blocks.py`
  - Store: `db_agents.py`, `db_submissions.py`, `db_profiles_admin.py`, `search.py`
  - Gmail: `gmail_models.py`, `gmail_mime.py`, `gmail_base.py`, `gmail_mail.py`, `gmail_thread.py`
- Frontend icons split into focused modules under `src/components/icons/`.

### Security

- Removed hardcoded Firebase web API credentials from `classic/frontend/lib/main.dart` in favor of compile-time environment variables.
- Documented that Postgres role passwords in `roles.sql` are injected from `POSTGRES_PASSWORD` at runtime and must be rotated if ever exposed.
