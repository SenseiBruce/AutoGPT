"""Airtable table/field schema API helpers."""

import base64
from enum import Enum
from logging import getLogger
from typing import Any
from urllib.parse import quote, urlencode

from backend.sdk import BaseModel, Credentials, Requests

logger = getLogger(__name__)

from ._api_types import TABLE_FIELD_TYPES, TableFieldType

async def create_table(
    credentials: Credentials,
    base_id: str,
    table_name: str,
    table_fields: list[dict],
) -> dict:
    for field in table_fields:
        assert field.get("name"), "Field name is required"
        assert (
            field.get("type") in TABLE_FIELD_TYPES
        ), f"Field type {field.get('type')} is not valid. Valid types are {TABLE_FIELD_TYPES}."
        # Note fields have differnet options for different types we are not currently validating them

    response = await Requests().post(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
        headers={"Authorization": credentials.auth_header()},
        json={
            "name": table_name,
            "fields": table_fields,
        },
    )

    return response.json()


async def update_table(
    credentials: Credentials,
    base_id: str,
    table_id: str,
    table_name: str | None = None,
    table_description: str | None = None,
    date_dependency: dict | None = None,
) -> dict:

    assert (
        table_name or table_description or date_dependency
    ), "At least one of table_name, table_description, or date_dependency must be provided"

    params: dict[str, str | dict[str, str]] = {}
    if table_name:
        params["name"] = table_name
    if table_description:
        params["description"] = table_description
    if date_dependency:
        params["dateDependency"] = date_dependency

    response = await Requests().patch(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}",
        headers={"Authorization": credentials.auth_header()},
        json=_convert_bools(params),
    )

    return response.json()


async def create_field(
    credentials: Credentials,
    base_id: str,
    table_id: str,
    field_type: TableFieldType,
    name: str,
    description: str | None = None,
    options: dict[str, str] | None = None,
) -> dict[str, str | dict[str, str]]:

    assert (
        field_type in TABLE_FIELD_TYPES
    ), f"Field type {field_type} is not valid. Valid types are {TABLE_FIELD_TYPES}."
    params: dict[str, str | dict[str, str]] = {}
    params["type"] = field_type
    params["name"] = name
    if description:
        params["description"] = description
    if options:
        params["options"] = options

    response = await Requests().post(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields",
        headers={"Authorization": credentials.auth_header()},
        json=_convert_bools(params),
    )
    return response.json()


async def update_field(
    credentials: Credentials,
    base_id: str,
    table_id: str,
    field_id: str,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, str]:

    assert name or description, "At least one of name or description must be provided"
    params: dict[str, str | dict[str, str]] = {}
    if name:
        params["name"] = name
    if description:
        params["description"] = description

    response = await Requests().patch(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables/{table_id}/fields/{field_id}",
        headers={"Authorization": credentials.auth_header()},
        json=_convert_bools(params),
    )
    return response.json()


#################################################################
# Record Management
#################################################################


async def get_table_schema(
    credentials: Credentials,
    base_id: str,
    table_id_or_name: str,
) -> dict:
    """
    Get the schema for a specific table, including all field definitions.

    Args:
        credentials: Airtable API credentials
        base_id: The base ID
        table_id_or_name: The table ID or name

    Returns:
        Dict containing table schema with fields information
    """
    # First get all tables to find the right one
    response = await Requests().get(
        f"https://api.airtable.com/v0/meta/bases/{base_id}/tables",
        headers={"Authorization": credentials.auth_header()},
    )

    data = response.json()
    tables = data.get("tables", [])

    # Find the matching table
    for table in tables:
        if table.get("id") == table_id_or_name or table.get("name") == table_id_or_name:
            return table

    raise ValueError(f"Table '{table_id_or_name}' not found in base '{base_id}'")


def get_empty_value_for_field(field_type: str) -> Any:
    """
    Return the appropriate empty value for a given Airtable field type.

    Args:
        field_type: The Airtable field type

    Returns:
        The appropriate empty value for that field type
    """
    # Fields that should be false when empty
    if field_type == "checkbox":
        return False

    # Fields that should be empty arrays
    if field_type in [
        "multipleSelects",
        "multipleRecordLinks",
        "multipleAttachments",
        "multipleLookupValues",
        "multipleCollaborators",
    ]:
        return []

    # Fields that should be 0 when empty (numeric types)
    if field_type in [
        "number",
        "percent",
        "currency",
        "rating",
        "duration",
        "count",
        "autoNumber",
    ]:
        return 0

    # Fields that should be empty strings
    if field_type in [
        "singleLineText",
        "multilineText",
        "email",
        "url",
        "phoneNumber",
        "richText",
        "barcode",
    ]:
        return ""

    # Everything else gets null (dates, single selects, formulas, etc.)
    return None


async def normalize_records(
    records: list[dict],
    table_schema: dict,
    include_field_metadata: bool = False,
) -> dict:
    """
    Normalize Airtable records to include all fields with proper empty values.

    Args:
        records: List of record objects from Airtable API
        table_schema: Table schema containing field definitions
        include_field_metadata: Whether to include field metadata in response

    Returns:
        Dict with normalized records and optionally field metadata
    """
    fields = table_schema.get("fields", [])

    # Normalize each record
    normalized_records = []
    for record in records:
        normalized = {
            "id": record.get("id"),
            "createdTime": record.get("createdTime"),
            "fields": {},
        }

        # Add existing fields
        existing_fields = record.get("fields", {})

        # Add all fields from schema, using empty values for missing ones
        for field in fields:
            field_name = field["name"]
            field_type = field["type"]

            if field_name in existing_fields:
                # Field exists, use its value
                normalized["fields"][field_name] = existing_fields[field_name]
            else:
                # Field is missing, add appropriate empty value
                normalized["fields"][field_name] = get_empty_value_for_field(field_type)

        normalized_records.append(normalized)

    # Build result dictionary
    if include_field_metadata:
        field_metadata = {}
        for field in fields:
            metadata = {"type": field["type"], "id": field["id"]}

            # Add type-specific metadata
            options = field.get("options", {})
            if field["type"] == "currency" and "symbol" in options:
                metadata["symbol"] = options["symbol"]
                metadata["precision"] = options.get("precision", 2)
            elif field["type"] == "duration" and "durationFormat" in options:
                metadata["format"] = options["durationFormat"]
            elif field["type"] == "percent" and "precision" in options:
                metadata["precision"] = options["precision"]
            elif (
                field["type"] in ["singleSelect", "multipleSelects"]
                and "choices" in options
            ):
                metadata["choices"] = [choice["name"] for choice in options["choices"]]
            elif field["type"] == "rating" and "max" in options:
                metadata["max"] = options["max"]
                metadata["icon"] = options.get("icon", "star")
                metadata["color"] = options.get("color", "yellowBright")

            field_metadata[field["name"]] = metadata

        return {"records": normalized_records, "field_metadata": field_metadata}
    else:
        return {"records": normalized_records}


