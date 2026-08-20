"""Airtable record CRUD API helpers."""

import base64
from enum import Enum
from logging import getLogger
from typing import Any
from urllib.parse import quote, urlencode

from backend.sdk import BaseModel, Credentials, Requests

logger = getLogger(__name__)

async def list_records(
    credentials: Credentials,
    base_id: str,
    table_id_or_name: str,
    # Query parameters
    time_zone: AirtableTimeZones | None = None,
    user_local: str | None = None,
    page_size: int | None = None,
    max_records: int | None = None,
    offset: str | None = None,
    view: str | None = None,
    sort: list[dict[str, str]] | None = None,
    filter_by_formula: str | None = None,
    cell_format: dict[str, str] | None = None,
    fields: list[str] | None = None,
    return_fields_by_field_id: bool | None = None,
    record_metadata: list[str] | None = None,
) -> dict[str, list[dict[str, dict[str, str]]]]:

    params: dict[str, str | dict[str, str] | list[dict[str, str]] | list[str]] = {}
    if time_zone:
        params["timeZone"] = time_zone
    if user_local:
        params["userLocal"] = user_local
    if page_size:
        params["pageSize"] = str(page_size)
    if max_records:
        params["maxRecords"] = str(max_records)
    if offset:
        params["offset"] = offset
    if view:
        params["view"] = view
    if sort:
        params["sort"] = sort
    if filter_by_formula:
        params["filterByFormula"] = filter_by_formula
    if cell_format:
        params["cellFormat"] = cell_format
    if fields:
        params["fields"] = fields
    if return_fields_by_field_id:
        params["returnFieldsByFieldId"] = str(return_fields_by_field_id)
    if record_metadata:
        params["recordMetadata"] = record_metadata

    response = await Requests().get(
        f"https://api.airtable.com/v0/{base_id}/{table_id_or_name}",
        headers={"Authorization": credentials.auth_header()},
        json=_convert_bools(params),
    )
    return response.json()


async def get_record(
    credentials: Credentials,
    base_id: str,
    table_id_or_name: str,
    record_id: str,
) -> dict[str, dict[str, dict[str, str]]]:

    response = await Requests().get(
        f"https://api.airtable.com/v0/{base_id}/{table_id_or_name}/{record_id}",
        headers={"Authorization": credentials.auth_header()},
    )
    return response.json()


async def update_multiple_records(
    credentials: Credentials,
    base_id: str,
    table_id_or_name: str,
    records: list[dict[str, dict[str, str]]],
    perform_upsert: dict[str, list[str]] | None = None,
    return_fields_by_field_id: bool | None = None,
    typecast: bool | None = None,
) -> dict[str, dict[str, dict[str, str]]]:

    params: dict[
        str, str | bool | dict[str, list[str]] | list[dict[str, dict[str, str]]]
    ] = {}
    if perform_upsert:
        params["performUpsert"] = perform_upsert
    if return_fields_by_field_id:
        params["returnFieldsByFieldId"] = str(return_fields_by_field_id)
    if typecast:
        params["typecast"] = typecast

    params["records"] = [_convert_bools(record) for record in records]

    response = await Requests().patch(
        f"https://api.airtable.com/v0/{base_id}/{table_id_or_name}",
        headers={"Authorization": credentials.auth_header()},
        json=_convert_bools(params),
    )
    return response.json()


async def update_record(
    credentials: Credentials,
    base_id: str,
    table_id_or_name: str,
    record_id: str,
    return_fields_by_field_id: bool | None = None,
    typecast: bool | None = None,
    fields: dict[str, Any] | None = None,
) -> dict[str, dict[str, dict[str, str]]]:
    params: dict[str, str | bool | dict[str, Any] | list[dict[str, dict[str, str]]]] = (
        {}
    )
    if return_fields_by_field_id:
        params["returnFieldsByFieldId"] = return_fields_by_field_id
    if typecast:
        params["typecast"] = typecast
    if fields:
        params["fields"] = fields

    response = await Requests().patch(
        f"https://api.airtable.com/v0/{base_id}/{table_id_or_name}/{record_id}",
        headers={"Authorization": credentials.auth_header()},
        json=_convert_bools(params),
    )
    return response.json()


async def create_record(
    credentials: Credentials,
    base_id: str,
    table_id_or_name: str,
    fields: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
    return_fields_by_field_id: bool | None = None,
    typecast: bool | None = None,
) -> dict[str, dict[str, dict[str, str]]]:
    assert fields or records, "At least one of fields or records must be provided"
    assert not (fields and records), "Only one of fields or records can be provided"
    if records is not None:
        assert (
            len(records) <= 10
        ), "Only up to 10 records can be provided when using records"

    params: dict[str, str | bool | dict[str, Any] | list[dict[str, Any]]] = {}
    if fields:
        params["fields"] = fields
    if records:
        params["records"] = records
    if return_fields_by_field_id:
        params["returnFieldsByFieldId"] = return_fields_by_field_id
    if typecast:
        params["typecast"] = typecast

    response = await Requests().post(
        f"https://api.airtable.com/v0/{base_id}/{table_id_or_name}",
        headers={"Authorization": credentials.auth_header()},
        json=_convert_bools(params),
    )

    return response.json()


async def delete_multiple_records(
    credentials: Credentials,
    base_id: str,
    table_id_or_name: str,
    records: list[str],
) -> dict[str, dict[str, dict[str, str]]]:

    query_string = "&".join([f"records[]={quote(record)}" for record in records])
    response = await Requests().delete(
        f"https://api.airtable.com/v0/{base_id}/{table_id_or_name}?{query_string}",
        headers={"Authorization": credentials.auth_header()},
    )
    return response.json()


async def delete_record(
    credentials: Credentials,
    base_id: str,
    table_id_or_name: str,
    record_id: str,
) -> dict[str, dict[str, dict[str, str]]]:

    response = await Requests().delete(
        f"https://api.airtable.com/v0/{base_id}/{table_id_or_name}/{record_id}",
        headers={"Authorization": credentials.auth_header()},
    )
    return response.json()


