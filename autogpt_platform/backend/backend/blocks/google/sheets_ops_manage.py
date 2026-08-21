"""Google Sheets manage/batch blocks."""

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


