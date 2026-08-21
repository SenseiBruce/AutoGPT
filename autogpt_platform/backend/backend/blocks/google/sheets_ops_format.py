"""Google Sheets format/create blocks."""

"""Google Sheets find/format/create blocks."""

"""Google Sheets manage/batch/find/format/create blocks."""

from typing import Any

from backend.blocks.google.sheets_helpers import (
    GOOGLE_SHEETS_DISABLED,
    BatchOperation,
    BatchOperationType,
    SheetOperation,
    ValueInputOption,
    _build_sheets_service,
    _convert_dicts_to_rows,
    _first_sheet_meta,
    extract_spreadsheet_id,
    format_sheet_name,
    get_all_sheet_names,
    parse_a1_notation,
    resolve_sheet_name,
    sheet_id_by_name,
)
from backend.data.block import (
    Block,
    BlockCategory,
    BlockOutput,
    BlockSchemaInput,
    BlockSchemaOutput,
)
from backend.data.model import SchemaField

from ._auth import (
    TEST_CREDENTIALS,
    TEST_CREDENTIALS_INPUT,
    GoogleCredentials,
    GoogleCredentialsField,
    GoogleCredentialsInput,
)

class GoogleSheetsFormatBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/spreadsheets"]
        )
        spreadsheet_id: str = SchemaField(
            description="Spreadsheet ID or URL",
            title="Spreadsheet ID or URL",
        )
        range: str = SchemaField(description="A1 notation – sheet optional")
        background_color: dict = SchemaField(default={})
        text_color: dict = SchemaField(default={})
        bold: bool = SchemaField(default=False)
        italic: bool = SchemaField(default=False)
        font_size: int = SchemaField(default=10)

    class Output(BlockSchemaOutput):
        result: dict = SchemaField(description="API response or success flag")

    def __init__(self):
        super().__init__(
            id="270f2384-8089-4b5b-b2e3-fe2ea3d87c02",
            description="Format a range in a Google Sheet (sheet optional)",
            categories={BlockCategory.DATA},
            input_schema=GoogleSheetsFormatBlock.Input,
            output_schema=GoogleSheetsFormatBlock.Output,
            disabled=GOOGLE_SHEETS_DISABLED,
            test_input={
                "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "range": "A1:B2",
                "background_color": {"red": 1.0, "green": 0.9, "blue": 0.9},
                "bold": True,
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[("result", {"success": True})],
            test_mock={"_format_cells": lambda *args, **kwargs: {"success": True}},
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = _build_sheets_service(credentials)
        spreadsheet_id = extract_spreadsheet_id(input_data.spreadsheet_id)
        result = await asyncio.to_thread(
            self._format_cells,
            service,
            spreadsheet_id,
            input_data.range,
            input_data.background_color,
            input_data.text_color,
            input_data.bold,
            input_data.italic,
            input_data.font_size,
        )
        if "error" in result:
            yield "error", result["error"]
        else:
            yield "result", result

    def _format_cells(
        self,
        service,
        spreadsheet_id: str,
        a1_range: str,
        background_color: dict,
        text_color: dict,
        bold: bool,
        italic: bool,
        font_size: int,
    ) -> dict:
        sheet_name, cell_range = parse_a1_notation(a1_range)
        sheet_name = resolve_sheet_name(service, spreadsheet_id, sheet_name)

        sheet_id = sheet_id_by_name(service, spreadsheet_id, sheet_name)
        if sheet_id is None:
            return {"error": f"Sheet '{sheet_name}' not found"}

        try:
            start_cell, end_cell = cell_range.split(":")
            start_col = ord(start_cell[0].upper()) - ord("A")
            start_row = int(start_cell[1:]) - 1
            end_col = ord(end_cell[0].upper()) - ord("A") + 1
            end_row = int(end_cell[1:])
        except (ValueError, IndexError):
            return {"error": f"Invalid range format: {a1_range}"}

        cell_format: dict = {"userEnteredFormat": {}}
        if background_color:
            cell_format["userEnteredFormat"]["backgroundColor"] = background_color

        text_format: dict = {}
        if text_color:
            text_format["foregroundColor"] = text_color
        if bold:
            text_format["bold"] = True
        if italic:
            text_format["italic"] = True
        if font_size != 10:
            text_format["fontSize"] = font_size
        if text_format:
            cell_format["userEnteredFormat"]["textFormat"] = text_format

        body = {
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": start_col,
                            "endColumnIndex": end_col,
                        },
                        "cell": cell_format,
                        "fields": "userEnteredFormat(backgroundColor,textFormat)",
                    }
                }
            ]
        }

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body=body
        ).execute()
        return {"success": True}


class GoogleSheetsCreateSpreadsheetBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/spreadsheets"]
        )
        title: str = SchemaField(
            description="The title of the new spreadsheet",
        )
        sheet_names: list[str] = SchemaField(
            description="List of sheet names to create (optional, defaults to single 'Sheet1')",
            default=["Sheet1"],
        )

    class Output(BlockSchemaOutput):
        result: dict = SchemaField(
            description="The result containing spreadsheet ID and URL",
        )
        spreadsheet_id: str = SchemaField(
            description="The ID of the created spreadsheet",
        )
        spreadsheet_url: str = SchemaField(
            description="The URL of the created spreadsheet",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="c8d4c0d3-c76e-4c2a-8c66-4119817ea3d1",
            description="This block creates a new Google Sheets spreadsheet with specified sheets.",
            categories={BlockCategory.DATA},
            input_schema=GoogleSheetsCreateSpreadsheetBlock.Input,
            output_schema=GoogleSheetsCreateSpreadsheetBlock.Output,
            disabled=GOOGLE_SHEETS_DISABLED,
            test_input={
                "title": "Test Spreadsheet",
                "sheet_names": ["Sheet1", "Data", "Summary"],
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("spreadsheet_id", "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"),
                (
                    "spreadsheet_url",
                    "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
                ),
                ("result", {"success": True}),
            ],
            test_mock={
                "_create_spreadsheet": lambda *args, **kwargs: {
                    "spreadsheetId": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                    "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
                },
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = _build_sheets_service(credentials)
        result = await asyncio.to_thread(
            self._create_spreadsheet,
            service,
            input_data.title,
            input_data.sheet_names,
        )

        if "error" in result:
            yield "error", result["error"]
        else:
            yield "spreadsheet_id", result["spreadsheetId"]
            yield "spreadsheet_url", result["spreadsheetUrl"]
            yield "result", {"success": True}

    def _create_spreadsheet(self, service, title: str, sheet_names: list[str]) -> dict:
        try:
            # Create the initial spreadsheet
            spreadsheet_body = {
                "properties": {"title": title},
                "sheets": [
                    {
                        "properties": {
                            "title": sheet_names[0] if sheet_names else "Sheet1"
                        }
                    }
                ],
            }

            result = service.spreadsheets().create(body=spreadsheet_body).execute()
            spreadsheet_id = result["spreadsheetId"]
            spreadsheet_url = result["spreadsheetUrl"]

            # Add additional sheets if requested
            if len(sheet_names) > 1:
                requests = []
                for sheet_name in sheet_names[1:]:
                    requests.append({"addSheet": {"properties": {"title": sheet_name}}})

                if requests:
                    batch_body = {"requests": requests}
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=spreadsheet_id, body=batch_body
                    ).execute()

            return {
                "spreadsheetId": spreadsheet_id,
                "spreadsheetUrl": spreadsheet_url,
            }
        except Exception as e:
            return {"error": str(e)}
