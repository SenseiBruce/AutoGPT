#!/usr/bin/env python3
"""Fail if curated platform env vars are missing from .env.example files."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = {
    ROOT / "autogpt_platform/backend/.env.example": [
        "DATABASE_URL",
        "REDIS_HOST",
        "OPENAI_API_KEY",
        "AIRTABLE_API_KEY",
        "FIRECRAWL_API_KEY",
        "OPENAI_INTERNAL_API_KEY",
        "APP_ENV",
    ],
    ROOT / "autogpt_platform/frontend/.env.example": [
        "NEXT_PUBLIC_SUPABASE_URL",
        "AUTH_CALLBACK_URL",
        "AGPT_SERVER_URL",
        "DISABLE_SENTRY",
    ],
}


def _declared_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def main() -> int:
    missing: list[str] = []
    for path, required in REQUIRED.items():
        if not path.is_file():
            missing.append(f"{path}: file missing")
            continue
        keys = _declared_keys(path)
        for key in required:
            if key not in keys:
                missing.append(f"{path.relative_to(ROOT)}: missing {key}")
    if missing:
        print("Env example gaps:")
        for item in missing:
            print(f"  - {item}")
        return 1
    print("Env examples cover required platform variables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
