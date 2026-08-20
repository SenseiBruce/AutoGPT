"""Structural checks for god-file split refactors."""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
    / "autogpt_platform"
    / "backend"
    / "backend"
)


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_entrypoint_modules_are_small():
    assert _line_count(BACKEND_ROOT / "blocks/llm.py") < 120
    assert _line_count(BACKEND_ROOT / "blocks/google/gmail.py") < 120
    assert _line_count(BACKEND_ROOT / "blocks/google/sheets.py") < 120
    assert _line_count(BACKEND_ROOT / "blocks/exa/websets.py") < 120
    assert _line_count(BACKEND_ROOT / "blocks/github/repo.py") < 120
    assert _line_count(BACKEND_ROOT / "blocks/discord/bot_blocks.py") < 120
    assert _line_count(BACKEND_ROOT / "server/v2/store/db.py") < 500
    assert _line_count(BACKEND_ROOT / "data/graph.py") < 120
    assert _line_count(BACKEND_ROOT / "data/execution.py") < 120
    assert _line_count(BACKEND_ROOT / "data/credit.py") < 120
    assert _line_count(BACKEND_ROOT / "server/v2/library/db.py") < 120
    assert _line_count(BACKEND_ROOT / "server/routers/v1.py") < 250


def test_no_oversized_split_helpers():
    """Buyer scanners count any file over 1000 LOC, not just entrypoints."""
    candidates = [
        BACKEND_ROOT / "blocks/llm_base.py",
        BACKEND_ROOT / "blocks/llm_structured.py",
        BACKEND_ROOT / "blocks/llm_text_blocks.py",
        BACKEND_ROOT / "blocks/llm_blocks.py",
        BACKEND_ROOT / "blocks/llm_call.py",
        BACKEND_ROOT / "blocks/llm_models.py",
        BACKEND_ROOT / "blocks/google/gmail_base.py",
        BACKEND_ROOT / "blocks/google/gmail_mail.py",
        BACKEND_ROOT / "blocks/google/gmail_thread.py",
        BACKEND_ROOT / "blocks/google/gmail_blocks.py",
        BACKEND_ROOT / "blocks/google/gmail_mime.py",
        BACKEND_ROOT / "blocks/google/gmail_models.py",
        BACKEND_ROOT / "blocks/google/sheets_helpers.py",
        BACKEND_ROOT / "blocks/google/sheets_crud.py",
        BACKEND_ROOT / "blocks/google/sheets_ops.py",
        BACKEND_ROOT / "blocks/exa/websets_create.py",
        BACKEND_ROOT / "blocks/exa/websets_manage.py",
        BACKEND_ROOT / "blocks/exa/websets_status.py",
        BACKEND_ROOT / "blocks/airtable/_api_types.py",
        BACKEND_ROOT / "blocks/airtable/_api_tables.py",
        BACKEND_ROOT / "blocks/airtable/_api_records.py",
        BACKEND_ROOT / "blocks/airtable/_api_webhooks.py",
        BACKEND_ROOT / "blocks/github/repo_list.py",
        BACKEND_ROOT / "blocks/github/repo_files.py",
        BACKEND_ROOT / "blocks/github/repo_mgmt.py",
        BACKEND_ROOT / "blocks/discord/bot_messaging.py",
        BACKEND_ROOT / "blocks/discord/bot_files.py",
        BACKEND_ROOT / "blocks/discord/bot_info.py",
        BACKEND_ROOT / "data/graph_models.py",
        BACKEND_ROOT / "data/graph_db.py",
        BACKEND_ROOT / "data/execution_models.py",
        BACKEND_ROOT / "data/execution_queries.py",
        BACKEND_ROOT / "data/execution_events.py",
        BACKEND_ROOT / "data/credit_base.py",
        BACKEND_ROOT / "data/credit_user.py",
        BACKEND_ROOT / "server/v2/library/db_agents.py",
        BACKEND_ROOT / "server/v2/library/db_presets.py",
        BACKEND_ROOT / "server/routers/v1_auth.py",
        BACKEND_ROOT / "server/routers/v1_blocks.py",
        BACKEND_ROOT / "server/routers/v1_credits.py",
        BACKEND_ROOT / "server/routers/v1_graphs.py",
        BACKEND_ROOT / "server/routers/v1_schedules.py",
        BACKEND_ROOT / "notifications/notifications_queue.py",
        BACKEND_ROOT / "notifications/notifications_batch.py",
        BACKEND_ROOT / "notifications/notifications.py",
        BACKEND_ROOT / "util/cache_thread_test.py",
        BACKEND_ROOT / "util/cache_cached_test.py",
        BACKEND_ROOT / "util/cache_shared_test.py",
        BACKEND_ROOT / "server/v2/store/db_agents.py",
        BACKEND_ROOT / "server/v2/store/db_submissions.py",
        BACKEND_ROOT / "server/v2/store/db_profiles_admin.py",
        BACKEND_ROOT / "server/v2/store/search.py",
    ]
    oversized = [
        str(p.relative_to(BACKEND_ROOT))
        for p in candidates
        if _line_count(p) > 1000
    ]
    assert oversized == [], f"files over 1000 LOC: {oversized}"


def test_no_backend_python_file_over_1000_loc():
    oversized = [
        str(p.relative_to(BACKEND_ROOT))
        for p in BACKEND_ROOT.rglob("*.py")
        if _line_count(p) > 1000
    ]
    assert oversized == [], f"files over 1000 LOC: {oversized}"


def test_extracted_modules_exist():
    expected = [
        "blocks/llm_models.py",
        "blocks/llm_call.py",
        "blocks/llm_base.py",
        "blocks/llm_structured.py",
        "blocks/llm_text_blocks.py",
        "blocks/llm_blocks.py",
        "blocks/google/gmail_models.py",
        "blocks/google/gmail_mime.py",
        "blocks/google/gmail_base.py",
        "blocks/google/gmail_mail.py",
        "blocks/google/gmail_thread.py",
        "blocks/google/gmail_blocks.py",
        "blocks/google/sheets_helpers.py",
        "blocks/google/sheets_crud.py",
        "blocks/google/sheets_ops.py",
        "blocks/exa/websets_create.py",
        "blocks/exa/websets_manage.py",
        "blocks/exa/websets_status.py",
        "blocks/airtable/_api_types.py",
        "blocks/airtable/_api_tables.py",
        "blocks/airtable/_api_records.py",
        "blocks/airtable/_api_webhooks.py",
        "blocks/github/repo_list.py",
        "blocks/github/repo_files.py",
        "blocks/github/repo_mgmt.py",
        "blocks/discord/bot_messaging.py",
        "blocks/discord/bot_files.py",
        "blocks/discord/bot_info.py",
        "data/graph_models.py",
        "data/graph_db.py",
        "data/execution_models.py",
        "data/execution_queries.py",
        "data/execution_events.py",
        "data/credit_base.py",
        "data/credit_user.py",
        "server/v2/library/db_agents.py",
        "server/v2/library/db_presets.py",
        "server/routers/v1_auth.py",
        "server/routers/v1_blocks.py",
        "server/routers/v1_credits.py",
        "server/routers/v1_graphs.py",
        "server/routers/v1_schedules.py",
        "notifications/notifications_queue.py",
        "notifications/notifications_batch.py",
        "util/cache_thread_test.py",
        "util/cache_cached_test.py",
        "util/cache_shared_test.py",
        "server/v2/store/db_agents.py",
        "server/v2/store/db_submissions.py",
        "server/v2/store/db_profiles_admin.py",
        "server/v2/store/search.py",
    ]
    for rel in expected:
        assert (BACKEND_ROOT / rel).is_file(), rel


def test_public_api_modules_reexport_symbols():
    llm = (BACKEND_ROOT / "blocks/llm.py").read_text(encoding="utf-8")
    gmail = (BACKEND_ROOT / "blocks/google/gmail.py").read_text(encoding="utf-8")
    sheets = (BACKEND_ROOT / "blocks/google/sheets.py").read_text(encoding="utf-8")
    websets = (BACKEND_ROOT / "blocks/exa/websets.py").read_text(encoding="utf-8")
    airtable = (BACKEND_ROOT / "blocks/airtable/_api.py").read_text(encoding="utf-8")
    repo = (BACKEND_ROOT / "blocks/github/repo.py").read_text(encoding="utf-8")
    discord = (BACKEND_ROOT / "blocks/discord/bot_blocks.py").read_text(encoding="utf-8")
    graph = (BACKEND_ROOT / "data/graph.py").read_text(encoding="utf-8")
    execution = (BACKEND_ROOT / "data/execution.py").read_text(encoding="utf-8")
    v1 = (BACKEND_ROOT / "server/routers/v1.py").read_text(encoding="utf-8")
    assert "AIStructuredResponseGeneratorBlock" in llm
    assert "LlmModel" in llm
    assert "GmailReadBlock" in gmail
    assert "GmailReplyBlock" in gmail
    assert "GoogleSheetsReadBlock" in sheets
    assert "ExaCreateWebsetBlock" in websets
    assert "list_records" in airtable
    assert "GithubReadFileBlock" in repo
    assert "SendDiscordMessageBlock" in discord
    assert "GraphModel" in graph
    assert "ExecutionStatus" in execution
    assert "execute_graph" in v1
    assert "v1_router" in v1

def test_store_agent_parsers_are_pure_functions():
    source = (BACKEND_ROOT / "server/v2/store/db_agents.py").read_text(encoding="utf-8")
    assert "def store_agent_from_raw_row" in source
    assert "def store_agent_from_prisma" in source
    assert "import prisma" not in source.split("def store_agent_from_raw_row")[0]
