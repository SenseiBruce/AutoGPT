"""Google Sheets helper utilities and shared types."""

import asyncio
from enum import Enum
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from backend.data.block import BlockSchemaInput
from backend.data.model import SchemaField
from backend.util.settings import Settings

from ._auth import (
    GOOGLE_OAUTH_IS_CONFIGURED,
    GoogleCredentials,
)

settings = Settings()
GOOGLE_SHEETS_DISABLED = not GOOGLE_OAUTH_IS_CONFIGURED


def parse_a1_notation(a1: str) -> tuple[str | None, str]:
    """Split an A1‑notation string into *(sheet_name, cell_range)*.

    Examples
    --------
    >>> parse_a1_notation("Sheet1!A1:B2")
    ("Sheet1", "A1:B2")
    >>> parse_a1_notation("A1:B2")
    (None, "A1:B2")
    """

    if "!" in a1:
        sheet, cell_range = a1.split("!", 1)
        return sheet, cell_range
    return None, a1


def extract_spreadsheet_id(spreadsheet_id_or_url: str) -> str:
    """Extract spreadsheet ID from either a direct ID or a Google Sheets URL.

    Examples
    --------
    >>> extract_spreadsheet_id("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")
    "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    >>> extract_spreadsheet_id("https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit")
    "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    """
    if "/spreadsheets/d/" in spreadsheet_id_or_url:
        # Extract ID from URL: https://docs.google.com/spreadsheets/d/{ID}/edit...
        parts = spreadsheet_id_or_url.split("/d/")[1].split("/")[0]
        return parts
    return spreadsheet_id_or_url


def format_sheet_name(sheet_name: str) -> str:
    """Format sheet name for Google Sheets API, adding quotes if needed.

    Examples
    --------
    >>> format_sheet_name("Sheet1")
    "Sheet1"
    >>> format_sheet_name("Non-matching Leads")
    "'Non-matching Leads'"
    """
    # If sheet name contains spaces, special characters, or starts with a digit, wrap in quotes
    if (
        " " in sheet_name
        or any(char in sheet_name for char in "!@#$%^&*()+-=[]{}|;:,.<>?")
        or (sheet_name and sheet_name[0].isdigit())
    ):
        return f"'{sheet_name}'"
    return sheet_name


def _first_sheet_meta(service, spreadsheet_id: str) -> tuple[str, int]:
    """Return *(title, sheetId)* for the first sheet in *spreadsheet_id*."""

    meta = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, includeGridData=False)
        .execute()
    )
    first = meta["sheets"][0]["properties"]
    return first["title"], first["sheetId"]


def get_all_sheet_names(service, spreadsheet_id: str) -> list[str]:
    """Get all sheet names in the spreadsheet."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return [
        sheet.get("properties", {}).get("title", "") for sheet in meta.get("sheets", [])
    ]


def resolve_sheet_name(service, spreadsheet_id: str, sheet_name: str | None) -> str:
    """Resolve *sheet_name*, falling back to the workbook's first sheet if empty.

    Validates that the sheet exists in the spreadsheet and provides helpful error info.
    """
    if sheet_name:
        # Validate that the sheet exists
        all_sheets = get_all_sheet_names(service, spreadsheet_id)
        if sheet_name not in all_sheets:
            raise ValueError(
                f'Sheet "{sheet_name}" not found in spreadsheet. '
                f"Available sheets: {all_sheets}"
            )
        return sheet_name
    title, _ = _first_sheet_meta(service, spreadsheet_id)
    return title


def sheet_id_by_name(service, spreadsheet_id: str, sheet_name: str) -> int | None:
    """Return the *sheetId* for *sheet_name* (or `None` if not found)."""

    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sh in meta.get("sheets", []):
        if sh.get("properties", {}).get("title") == sheet_name:
            return sh["properties"]["sheetId"]
    return None


def _convert_dicts_to_rows(
    data: list[dict[str, Any]], headers: list[str]
) -> list[list[str]]:
    """Convert list of dictionaries to list of rows using the specified header order.

    Args:
        data: List of dictionaries to convert
        headers: List of column headers to use for ordering

    Returns:
        List of rows where each row is a list of string values in header order
    """
    if not data:
        return []

    if not headers:
        raise ValueError("Headers are required when using list[dict] format")

    rows = []
    for item in data:
        row = []
        for header in headers:
            value = item.get(header, "")
            row.append(str(value) if value is not None else "")
        rows.append(row)

    return rows


def _build_sheets_service(credentials: GoogleCredentials):
    settings = Settings()
    creds = Credentials(
        token=(
            credentials.access_token.get_secret_value()
            if credentials.access_token
            else None
        ),
        refresh_token=(
            credentials.refresh_token.get_secret_value()
            if credentials.refresh_token
            else None
        ),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.secrets.google_client_id,
        client_secret=settings.secrets.google_client_secret,
        scopes=credentials.scopes,
    )
    return build("sheets", "v4", credentials=creds)


class SheetOperation(str, Enum):
    CREATE = "create"
    DELETE = "delete"
    COPY = "copy"


class ValueInputOption(str, Enum):
    RAW = "RAW"
    USER_ENTERED = "USER_ENTERED"


class InsertDataOption(str, Enum):
    OVERWRITE = "OVERWRITE"
    INSERT_ROWS = "INSERT_ROWS"


class BatchOperationType(str, Enum):
    UPDATE = "update"
    CLEAR = "clear"


class BatchOperation(BlockSchemaInput):
    type: BatchOperationType = SchemaField(
        description="The type of operation to perform"
    )
    range: str = SchemaField(description="The A1 notation range for the operation")
    values: list[list[str]] = SchemaField(
        description="Values to update (only for UPDATE)", default=[]
    )


