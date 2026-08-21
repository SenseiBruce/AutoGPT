"""Google Sheets find blocks."""

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


