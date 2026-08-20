"""Structural checks for god-file split refactors."""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "autogpt_platform" / "backend" / "backend"


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_entrypoint_modules_are_small():
    assert _line_count(BACKEND_ROOT / "blocks/llm.py") < 120
    assert _line_count(BACKEND_ROOT / "blocks/google/gmail.py") < 120
    assert _line_count(BACKEND_ROOT / "server/v2/store/db.py") < 500


def test_extracted_modules_exist():
    expected = [
        "blocks/llm_models.py",
        "blocks/llm_call.py",
        "blocks/llm_blocks.py",
        "blocks/google/gmail_models.py",
        "blocks/google/gmail_mime.py",
        "blocks/google/gmail_blocks.py",
        "server/v2/store/db_agents.py",
        "server/v2/store/db_submissions.py",
        "server/v2/store/search.py",
    ]
    for rel in expected:
        assert (BACKEND_ROOT / rel).is_file(), rel


def test_store_agent_parsers_are_pure_functions():
    source = (BACKEND_ROOT / "server/v2/store/db_agents.py").read_text(encoding="utf-8")
    assert "def store_agent_from_raw_row" in source
    assert "def store_agent_from_prisma" in source
    assert "import prisma" not in source.split("def store_agent_from_raw_row")[0]
