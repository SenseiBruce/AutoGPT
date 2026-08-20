"""Google Sheets read/write/append/clear/metadata blocks."""

from typing import Any

from backend.blocks.google.sheets_helpers import (
    GOOGLE_SHEETS_DISABLED,
    InsertDataOption,
    ValueInputOption,
    _build_sheets_service,
    _convert_dicts_to_rows,
    extract_spreadsheet_id,
    format_sheet_name,
    parse_a1_notation,
    resolve_sheet_name,
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

class GoogleSheetsReadBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        spreadsheet_id: str = SchemaField(
            description="The ID or URL of the spreadsheet to read from",
            title="Spreadsheet ID or URL",
        )
        range: str = SchemaField(
            description="The A1 notation of the range to read",
        )

    class Output(BlockSchemaOutput):
        result: list[list[str]] = SchemaField(
            description="The data read from the spreadsheet",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="5724e902-3635-47e9-a108-aaa0263a4988",
            description="This block reads data from a Google Sheets spreadsheet.",
            categories={BlockCategory.DATA},
            input_schema=GoogleSheetsReadBlock.Input,
            output_schema=GoogleSheetsReadBlock.Output,
            disabled=GOOGLE_SHEETS_DISABLED,
            test_input={
                "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "range": "Sheet1!A1:B2",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "result",
                    [
                        ["Name", "Score"],
                        ["Alice", "85"],
                    ],
                ),
            ],
            test_mock={
                "_read_sheet": lambda *args, **kwargs: [
                    ["Name", "Score"],
                    ["Alice", "85"],
                ],
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = _build_sheets_service(credentials)
        spreadsheet_id = extract_spreadsheet_id(input_data.spreadsheet_id)
        data = await asyncio.to_thread(
            self._read_sheet, service, spreadsheet_id, input_data.range
        )
        yield "result", data

    def _read_sheet(self, service, spreadsheet_id: str, range: str) -> list[list[str]]:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range).execute()
        return result.get("values", [])


class GoogleSheetsWriteBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/spreadsheets"]
        )
        spreadsheet_id: str = SchemaField(
            description="The ID or URL of the spreadsheet to write to",
            title="Spreadsheet ID or URL",
        )
        range: str = SchemaField(
            description="The A1 notation of the range to write",
        )
        values: list[list[str]] = SchemaField(
            description="The data to write to the spreadsheet",
        )

    class Output(BlockSchemaOutput):
        result: dict = SchemaField(
            description="The result of the write operation",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="d9291e87-301d-47a8-91fe-907fb55460e5",
            description="This block writes data to a Google Sheets spreadsheet.",
            categories={BlockCategory.DATA},
            input_schema=GoogleSheetsWriteBlock.Input,
            output_schema=GoogleSheetsWriteBlock.Output,
            disabled=GOOGLE_SHEETS_DISABLED,
            test_input={
                "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "range": "Sheet1!A1:B2",
                "values": [
                    ["Name", "Score"],
                    ["Bob", "90"],
                ],
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "result",
                    {"updatedCells": 4, "updatedColumns": 2, "updatedRows": 2},
                ),
            ],
            test_mock={
                "_write_sheet": lambda *args, **kwargs: {
                    "updatedCells": 4,
                    "updatedColumns": 2,
                    "updatedRows": 2,
                },
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = _build_sheets_service(credentials)
        spreadsheet_id = extract_spreadsheet_id(input_data.spreadsheet_id)
        result = await asyncio.to_thread(
            self._write_sheet,
            service,
            spreadsheet_id,
            input_data.range,
            input_data.values,
        )
        yield "result", result

    def _write_sheet(
        self, service, spreadsheet_id: str, range: str, values: list[list[str]]
    ) -> dict:
        body = {"values": values}
        result = (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range,
                valueInputOption="USER_ENTERED",
                body=body,
            )
            .execute()
        )
        return result


class GoogleSheetsAppendBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/spreadsheets"]
        )
        spreadsheet_id: str = SchemaField(
            description="Spreadsheet ID or URL",
            title="Spreadsheet ID or URL",
        )
        sheet_name: str = SchemaField(
            description="Optional sheet to append to (defaults to first sheet)",
            default="",
        )
        values: list[list[str]] = SchemaField(
            description="Rows to append as list of rows (list[list[str]])",
            default=[],
        )
        dict_values: list[dict[str, Any]] = SchemaField(
            description="Rows to append as list of dictionaries (list[dict])",
            default=[],
        )
        headers: list[str] = SchemaField(
            description="Column headers to use for ordering dict values (required when dict_values is provided)",
            default=[],
        )
        range: str = SchemaField(
            description="Range to append to (e.g. 'A:A' for column A only, 'A:C' for columns A-C, or leave empty for unlimited columns). When empty, data will span as many columns as needed.",
            default="",
            advanced=True,
        )
        value_input_option: ValueInputOption = SchemaField(
            description="How input data should be interpreted",
            default=ValueInputOption.USER_ENTERED,
            advanced=True,
        )
        insert_data_option: InsertDataOption = SchemaField(
            description="How new data should be inserted",
            default=InsertDataOption.INSERT_ROWS,
            advanced=True,
        )

    class Output(BlockSchemaOutput):
        result: dict = SchemaField(description="Append API response")

    def __init__(self):
        super().__init__(
            id="531d50c0-d6b9-4cf9-a013-7bf783d313c7",
            description="Append data to a Google Sheet. Use 'values' for list of rows (list[list[str]]) or 'dict_values' with 'headers' for list of dictionaries (list[dict]). Data is added to the next empty row without overwriting existing content. Leave range empty for unlimited columns, or specify range like 'A:A' to constrain to specific columns.",
            categories={BlockCategory.DATA},
            input_schema=GoogleSheetsAppendBlock.Input,
            output_schema=GoogleSheetsAppendBlock.Output,
            disabled=GOOGLE_SHEETS_DISABLED,
            test_input={
                "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "values": [["Charlie", "95"]],
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("result", {"updatedCells": 2, "updatedColumns": 2, "updatedRows": 1}),
            ],
            test_mock={
                "_append_sheet": lambda *args, **kwargs: {
                    "updatedCells": 2,
                    "updatedColumns": 2,
                    "updatedRows": 1,
                },
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = _build_sheets_service(credentials)
        spreadsheet_id = extract_spreadsheet_id(input_data.spreadsheet_id)
        # Determine which values to use and convert if needed
        processed_values: list[list[str]]

        # Validate that only one format is provided
        if input_data.values and input_data.dict_values:
            raise ValueError("Provide either 'values' or 'dict_values', not both")

        if input_data.dict_values:
            if not input_data.headers:
                raise ValueError("Headers are required when using dict_values")
            processed_values = _convert_dicts_to_rows(
                input_data.dict_values, input_data.headers
            )
        elif input_data.values:
            processed_values = input_data.values
        else:
            raise ValueError("Either 'values' or 'dict_values' must be provided")

        result = await asyncio.to_thread(
            self._append_sheet,
            service,
            spreadsheet_id,
            input_data.sheet_name,
            processed_values,
            input_data.range,
            input_data.value_input_option,
            input_data.insert_data_option,
        )
        yield "result", result

    def _append_sheet(
        self,
        service,
        spreadsheet_id: str,
        sheet_name: str,
        values: list[list[str]],
        range: str,
        value_input_option: ValueInputOption,
        insert_data_option: InsertDataOption,
    ) -> dict:
        target_sheet = resolve_sheet_name(service, spreadsheet_id, sheet_name)
        formatted_sheet = format_sheet_name(target_sheet)
        # If no range specified, use A1 to let Google Sheets find the next empty row with unlimited columns
        # If range specified, use it to constrain columns (e.g., A:A for column A only)
        if range:
            append_range = f"{formatted_sheet}!{range}"
        else:
            # Use A1 as starting point for unlimited columns - Google Sheets will find next empty row
            append_range = f"{formatted_sheet}!A1"
        body = {"values": values}
        return (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=append_range,
                valueInputOption=value_input_option.value,
                insertDataOption=insert_data_option.value,
                body=body,
            )
            .execute()
        )


class GoogleSheetsClearBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/spreadsheets"]
        )
        spreadsheet_id: str = SchemaField(
            description="The ID or URL of the spreadsheet to clear",
            title="Spreadsheet ID or URL",
        )
        range: str = SchemaField(
            description="The A1 notation of the range to clear",
        )

    class Output(BlockSchemaOutput):
        result: dict = SchemaField(
            description="The result of the clear operation",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="84938266-0fc7-46e5-9369-adb0f6ae8015",
            description="This block clears data from a specified range in a Google Sheets spreadsheet.",
            categories={BlockCategory.DATA},
            input_schema=GoogleSheetsClearBlock.Input,
            output_schema=GoogleSheetsClearBlock.Output,
            disabled=GOOGLE_SHEETS_DISABLED,
            test_input={
                "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "range": "Sheet1!A1:B2",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                ("result", {"clearedRange": "Sheet1!A1:B2"}),
            ],
            test_mock={
                "_clear_range": lambda *args, **kwargs: {
                    "clearedRange": "Sheet1!A1:B2"
                },
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = _build_sheets_service(credentials)
        spreadsheet_id = extract_spreadsheet_id(input_data.spreadsheet_id)
        result = await asyncio.to_thread(
            self._clear_range,
            service,
            spreadsheet_id,
            input_data.range,
        )
        yield "result", result

    def _clear_range(self, service, spreadsheet_id: str, range: str) -> dict:
        result = (
            service.spreadsheets()
            .values()
            .clear(spreadsheetId=spreadsheet_id, range=range)
            .execute()
        )
        return result


class GoogleSheetsMetadataBlock(Block):
    class Input(BlockSchemaInput):
        credentials: GoogleCredentialsInput = GoogleCredentialsField(
            ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        spreadsheet_id: str = SchemaField(
            description="The ID or URL of the spreadsheet to get metadata for",
            title="Spreadsheet ID or URL",
        )

    class Output(BlockSchemaOutput):
        result: dict = SchemaField(
            description="The metadata of the spreadsheet including sheets info",
        )
        error: str = SchemaField(
            description="Error message if any",
        )

    def __init__(self):
        super().__init__(
            id="6a0be6ee-7a0d-4c92-819b-500630846ad0",
            description="This block retrieves metadata about a Google Sheets spreadsheet including sheet names and properties.",
            categories={BlockCategory.DATA},
            input_schema=GoogleSheetsMetadataBlock.Input,
            output_schema=GoogleSheetsMetadataBlock.Output,
            disabled=GOOGLE_SHEETS_DISABLED,
            test_input={
                "spreadsheet_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "credentials": TEST_CREDENTIALS_INPUT,
            },
            test_credentials=TEST_CREDENTIALS,
            test_output=[
                (
                    "result",
                    {
                        "title": "Test Spreadsheet",
                        "sheets": [{"title": "Sheet1", "sheetId": 0}],
                    },
                ),
            ],
            test_mock={
                "_get_metadata": lambda *args, **kwargs: {
                    "title": "Test Spreadsheet",
                    "sheets": [{"title": "Sheet1", "sheetId": 0}],
                },
            },
        )

    async def run(
        self, input_data: Input, *, credentials: GoogleCredentials, **kwargs
    ) -> BlockOutput:
        service = _build_sheets_service(credentials)
        spreadsheet_id = extract_spreadsheet_id(input_data.spreadsheet_id)
        result = await asyncio.to_thread(
            self._get_metadata,
            service,
            spreadsheet_id,
        )
        yield "result", result

    def _get_metadata(self, service, spreadsheet_id: str) -> dict:
        result = (
            service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, includeGridData=False)
            .execute()
        )
        return {
            "title": result.get("properties", {}).get("title"),
            "sheets": [
                {
                    "title": sheet.get("properties", {}).get("title"),
                    "sheetId": sheet.get("properties", {}).get("sheetId"),
                    "gridProperties": sheet.get("properties", {}).get(
                        "gridProperties", {}
                    ),
                }
                for sheet in result.get("sheets", [])
            ],
        }


