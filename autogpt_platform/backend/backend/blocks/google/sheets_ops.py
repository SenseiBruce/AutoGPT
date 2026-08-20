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

class GoogleSheetsManageSheetBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/spreadsheets"]
        )
        spreadsheet_id: str = SchemaField(
            description="Spreadsheet ID or URL",
            title="Spreadsheet ID or URL",
        )
        operation: SheetOperation = SchemaField(description="Operation to perform")
        sheet_name: str = SchemaField(
            description="Target sheet name (defaults to first sheet for delete)",
            default="",
        )
        source_sheet_id: int = SchemaField(
            description="Source sheet ID for copy", default=0
        )
        destination_sheet_name: str = SchemaField(
            description="New sheet name for copy", default=""
        )

    class Output(BlockSchemaOutput):
        result: dict = SchemaField(description="Operation result")

    def __init__(self):
        super().__init__(
            id="7940189d-b137-4ef1-aa18-3dd9a5bde9f3",
            description="Create, delete, or copy sheets (sheet optional)",
            categories={BlockCategory.DATA},
            input_schema=GoogleSheetsManageSheetBlock.Input,
            output_schema=GoogleSheetsManageSheetBlock.Output,
            disabled=GOOGLE_SHEETS_DISABLED,
            test_input={
                "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "operation": SheetOperation.CREATE,
                "sheet_name": "NewSheet",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[("result", {"success": True, "sheetId": 123})],
            test_mock={
                "_manage_sheet": lambda *args, **kwargs: {
                    "success": True,
                    "sheetId": 123,
                }
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = _build_sheets_service(credentials)
        spreadsheet_id = extract_spreadsheet_id(input_data.spreadsheet_id)
        result = await asyncio.to_thread(
            self._manage_sheet,
            service,
            spreadsheet_id,
            input_data.operation,
            input_data.sheet_name,
            input_data.source_sheet_id,
            input_data.destination_sheet_name,
        )
        yield "result", result

    def _manage_sheet(
        self,
        service,
        spreadsheet_id: str,
        operation: SheetOperation,
        sheet_name: str,
        source_sheet_id: int,
        destination_sheet_name: str,
    ) -> dict:
        requests = []

        # Ensure a target sheet name when needed
        target_name = resolve_sheet_name(service, spreadsheet_id, sheet_name)

        if operation == SheetOperation.CREATE:
            requests.append({"addSheet": {"properties": {"title": target_name}}})
        elif operation == SheetOperation.DELETE:
            sid = sheet_id_by_name(service, spreadsheet_id, target_name)
            if sid is None:
                return {"error": f"Sheet '{target_name}' not found"}
            requests.append({"deleteSheet": {"sheetId": sid}})
        elif operation == SheetOperation.COPY:
            requests.append(
                {
                    "duplicateSheet": {
                        "sourceSheetId": source_sheet_id,
                        "newSheetName": destination_sheet_name
                        or f"Copy of {source_sheet_id}",
                    }
                }
            )
        else:
            return {"error": f"Unknown operation: {operation}"}

        body = {"requests": requests}
        result = (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
            .execute()
        )
        return {"success": True, "result": result}


class GoogleSheetsBatchOperationsBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/spreadsheets"]
        )
        spreadsheet_id: str = SchemaField(
            description="The ID or URL of the spreadsheet to perform batch operations on",
            title="Spreadsheet ID or URL",
        )
        operations: list[BatchOperation] = SchemaField(
            description="List of operations to perform",
        )

    class Output(BlockSchemaOutput):
        result: dict = SchemaField(
            description="The result of the batch operations",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="a4078584-6fe5-46e0-997e-d5126cdd112a",
            description="This block performs multiple operations on a Google Sheets spreadsheet in a single batch request.",
            categories={BlockCategory.DATA},
            input_schema=GoogleSheetsBatchOperationsBlock.Input,
            output_schema=GoogleSheetsBatchOperationsBlock.Output,
            disabled=GOOGLE_SHEETS_DISABLED,
            test_input={
                "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "operations": [
                    {
                        "type": BatchOperationType.UPDATE,
                        "range": "A1:B1",
                        "values": [["Header1", "Header2"]],
                    },
                    {
                        "type": BatchOperationType.UPDATE,
                        "range": "A2:B2",
                        "values": [["Data1", "Data2"]],
                    },
                ],
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("result", {"totalUpdatedCells": 4, "replies": []}),
            ],
            test_mock={
                "_batch_operations": lambda *args, **kwargs: {
                    "totalUpdatedCells": 4,
                    "replies": [],
                },
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = _build_sheets_service(credentials)
        spreadsheet_id = extract_spreadsheet_id(input_data.spreadsheet_id)
        result = await asyncio.to_thread(
            self._batch_operations,
            service,
            spreadsheet_id,
            input_data.operations,
        )
        yield "result", result

    def _batch_operations(
        self, service, spreadsheet_id: str, operations: list[BatchOperation]
    ) -> dict:
        update_data = []
        clear_ranges = []

        for op in operations:
            if op.type == BatchOperationType.UPDATE:
                update_data.append(
                    {
                        "range": op.range,
                        "values": op.values,
                    }
                )
            elif op.type == BatchOperationType.CLEAR:
                clear_ranges.append(op.range)

        results = {}

        # Perform updates if any
        if update_data:
            update_body = {
                "valueInputOption": "USER_ENTERED",
                "data": update_data,
            }
            update_result = (
                service.spreadsheets()
                .values()
                .batchUpdate(spreadsheetId=spreadsheet_id, body=update_body)
                .execute()
            )
            results["updateResult"] = update_result

        # Perform clears if any
        if clear_ranges:
            clear_body = {"ranges": clear_ranges}
            clear_result = (
                service.spreadsheets()
                .values()
                .batchClear(spreadsheetId=spreadsheet_id, body=clear_body)
                .execute()
            )
            results["clearResult"] = clear_result

        return results


class GoogleSheetsFindReplaceBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/spreadsheets"]
        )
        spreadsheet_id: str = SchemaField(
            description="The ID or URL of the spreadsheet to perform find/replace on",
            title="Spreadsheet ID or URL",
        )
        find_text: str = SchemaField(
            description="The text to find",
        )
        replace_text: str = SchemaField(
            description="The text to replace with",
        )
        sheet_id: int = SchemaField(
            description="The ID of the specific sheet to search (optional, searches all sheets if not provided)",
            default=-1,
        )
        match_case: bool = SchemaField(
            description="Whether to match case",
            default=False,
        )
        match_entire_cell: bool = SchemaField(
            description="Whether to match entire cell",
            default=False,
        )

    class Output(BlockSchemaOutput):
        result: dict = SchemaField(
            description="The result of the find/replace operation including number of replacements",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="accca760-8174-4656-b55e-5f0e82fee986",
            description="This block finds and replaces text in a Google Sheets spreadsheet.",
            categories={BlockCategory.DATA},
            input_schema=GoogleSheetsFindReplaceBlock.Input,
            output_schema=GoogleSheetsFindReplaceBlock.Output,
            disabled=GOOGLE_SHEETS_DISABLED,
            test_input={
                "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "find_text": "old_value",
                "replace_text": "new_value",
                "match_case": False,
                "match_entire_cell": False,
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("result", {"occurrencesChanged": 5}),
            ],
            test_mock={
                "_find_replace": lambda *args, **kwargs: {"occurrencesChanged": 5},
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = _build_sheets_service(credentials)
        spreadsheet_id = extract_spreadsheet_id(input_data.spreadsheet_id)
        result = await asyncio.to_thread(
            self._find_replace,
            service,
            spreadsheet_id,
            input_data.find_text,
            input_data.replace_text,
            input_data.sheet_id,
            input_data.match_case,
            input_data.match_entire_cell,
        )
        yield "result", result

    def _find_replace(
        self,
        service,
        spreadsheet_id: str,
        find_text: str,
        replace_text: str,
        sheet_id: int,
        match_case: bool,
        match_entire_cell: bool,
    ) -> dict:
        find_replace_request = {
            "find": find_text,
            "replacement": replace_text,
            "matchCase": match_case,
            "matchEntireCell": match_entire_cell,
        }

        if sheet_id >= 0:
            find_replace_request["sheetId"] = sheet_id

        requests = [{"findReplace": find_replace_request}]
        body = {"requests": requests}

        result = (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
            .execute()
        )

        return result


class GoogleSheetsFindBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        spreadsheet_id: str = SchemaField(
            description="The ID or URL of the spreadsheet to search in",
            title="Spreadsheet ID or URL",
        )
        find_text: str = SchemaField(
            description="The text to find",
        )
        sheet_id: int = SchemaField(
            description="The ID of the specific sheet to search (optional, searches all sheets if not provided)",
            default=-1,
        )
        match_case: bool = SchemaField(
            description="Whether to match case",
            default=False,
        )
        match_entire_cell: bool = SchemaField(
            description="Whether to match entire cell",
            default=False,
        )
        find_all: bool = SchemaField(
            description="Whether to find all occurrences (true) or just the first one (false)",
            default=True,
        )
        range: str = SchemaField(
            description="The A1 notation range to search in (optional, searches entire sheet if not provided)",
            default="",
            advanced=True,
        )

    class Output(BlockSchemaOutput):
        result: dict = SchemaField(
            description="The result of the find operation including locations and count",
        )
        locations: list[dict] = SchemaField(
            description="List of cell locations where the text was found",
        )
        count: int = SchemaField(
            description="Number of occurrences found",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="0f4ecc72-b958-47b2-b65e-76d6d26b9b27",
            description="Find text in a Google Sheets spreadsheet. Returns locations and count of occurrences. Can find all occurrences or just the first one.",
            categories={BlockCategory.DATA},
            input_schema=GoogleSheetsFindBlock.Input,
            output_schema=GoogleSheetsFindBlock.Output,
            disabled=GOOGLE_SHEETS_DISABLED,
            test_input={
                "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "find_text": "search_value",
                "match_case": False,
                "match_entire_cell": False,
                "find_all": True,
                "range": "Sheet1!A1:C10",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("count", 3),
                (
                    "locations",
                    [
                        {"sheet": "Sheet1", "row": 2, "column": 1, "address": "A2"},
                        {"sheet": "Sheet1", "row": 5, "column": 3, "address": "C5"},
                        {"sheet": "Sheet2", "row": 1, "column": 2, "address": "B1"},
                    ],
                ),
                ("result", {"success": True}),
            ],
            test_mock={
                "_find_text": lambda *args, **kwargs: {
                    "locations": [
                        {"sheet": "Sheet1", "row": 2, "column": 1, "address": "A2"},
                        {"sheet": "Sheet1", "row": 5, "column": 3, "address": "C5"},
                        {"sheet": "Sheet2", "row": 1, "column": 2, "address": "B1"},
                    ],
                    "count": 3,
                },
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = _build_sheets_service(credentials)
        spreadsheet_id = extract_spreadsheet_id(input_data.spreadsheet_id)
        result = await asyncio.to_thread(
            self._find_text,
            service,
            spreadsheet_id,
            input_data.find_text,
            input_data.sheet_id,
            input_data.match_case,
            input_data.match_entire_cell,
            input_data.find_all,
            input_data.range,
        )
        yield "count", result["count"]
        yield "locations", result["locations"]
        yield "result", {"success": True}

    def _find_text(
        self,
        service,
        spreadsheet_id: str,
        find_text: str,
        sheet_id: int,
        match_case: bool,
        match_entire_cell: bool,
        find_all: bool,
        range: str,
    ) -> dict:
        # Unfortunately, Google Sheets API doesn't have a dedicated "find-only" operation
        # that returns cell locations. The findReplace operation only returns a count.
        # So we need to search through the values manually to get location details.

        locations = []
        search_range = range if range else None

        if not search_range:
            # If no range specified, search entire spreadsheet
            meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = meta.get("sheets", [])

            # Filter to specific sheet if provided
            if sheet_id >= 0:
                sheets = [
                    s
                    for s in sheets
                    if s.get("properties", {}).get("sheetId") == sheet_id
                ]

            # Search each sheet
            for sheet in sheets:
                sheet_name = sheet.get("properties", {}).get("title", "")
                sheet_range = f"'{sheet_name}'"
                self._search_range(
                    service,
                    spreadsheet_id,
                    sheet_range,
                    sheet_name,
                    find_text,
                    match_case,
                    match_entire_cell,
                    find_all,
                    locations,
                )
                if not find_all and locations:
                    break
        else:
            # Search specific range
            sheet_name, cell_range = parse_a1_notation(search_range)
            if not sheet_name:
                # Get first sheet name if not specified
                meta = (
                    service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                )
                sheet_name = (
                    meta.get("sheets", [{}])[0]
                    .get("properties", {})
                    .get("title", "Sheet1")
                )
                search_range = f"'{sheet_name}'!{search_range}"

            self._search_range(
                service,
                spreadsheet_id,
                search_range,
                sheet_name,
                find_text,
                match_case,
                match_entire_cell,
                find_all,
                locations,
            )

        return {"locations": locations, "count": len(locations)}

    def _search_range(
        self,
        service,
        spreadsheet_id: str,
        range_name: str,
        sheet_name: str,
        find_text: str,
        match_case: bool,
        match_entire_cell: bool,
        find_all: bool,
        locations: list,
    ):
        """Search within a specific range and add results to locations list."""
        values_result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        values = values_result.get("values", [])

        # Parse range to get starting position
        _, cell_range = parse_a1_notation(range_name)
        start_col = 0
        start_row = 0

        if cell_range and ":" in cell_range:
            start_cell = cell_range.split(":")[0]
            # Parse A1 notation (e.g., "B3" -> col=1, row=2)
            col_part = ""
            row_part = ""
            for char in start_cell:
                if char.isalpha():
                    col_part += char
                elif char.isdigit():
                    row_part += char

            if col_part:
                start_col = ord(col_part.upper()) - ord("A")
            if row_part:
                start_row = int(row_part) - 1

        # Search through values
        for row_idx, row in enumerate(values):
            for col_idx, cell_value in enumerate(row):
                if cell_value is None:
                    continue

                cell_str = str(cell_value)

                # Apply search criteria
                search_text = find_text if match_case else find_text.lower()
                cell_text = cell_str if match_case else cell_str.lower()

                found = False
                if match_entire_cell:
                    found = cell_text == search_text
                else:
                    found = search_text in cell_text

                if found:
                    # Calculate actual spreadsheet position
                    actual_row = start_row + row_idx + 1
                    actual_col = start_col + col_idx + 1
                    col_letter = chr(ord("A") + start_col + col_idx)
                    address = f"{col_letter}{actual_row}"

                    location = {
                        "sheet": sheet_name,
                        "row": actual_row,
                        "column": actual_col,
                        "address": address,
                        "value": cell_str,
                    }
                    locations.append(location)

                    # Stop after first match if find_all is False
                    if not find_all:
                        return


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
