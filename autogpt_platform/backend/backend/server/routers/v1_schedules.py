"""Schedules and API key routes."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Annotated, Any, Sequence

import pydantic
import stripe
from autogpt_libs.auth import get_user_id, requires_user
from autogpt_libs.auth.jwt_utils import get_jwt_payload
from fastapi import (
    APIRouter,
    Body,
    File,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    Security,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from starlette.status import HTTP_204_NO_CONTENT, HTTP_404_NOT_FOUND
from typing_extensions import Optional, TypedDict

from backend.data.block import BlockInput, CompletedBlockOutput
from backend.data.credit import (
    AutoTopUpConfig,
    RefundRequest,
    TransactionHistory,
    UserCredit,
)
from backend.data.execution import UserContext
from backend.data.model import CredentialsMetaInput
from backend.data.notifications import NotificationPreference, NotificationPreferenceDTO
from backend.data.onboarding import UserOnboardingUpdate
from backend.server.model import (
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    CreateGraph,
    RequestTopUp,
    SetGraphActiveVersion,
    TimezoneResponse,
    UpdatePermissionsRequest,
    UpdateTimezoneRequest,
    UploadFileResponse,
)
from backend.util.cache import cached
from backend.util.exceptions import GraphValidationError, NotFoundError
from backend.util.json import dumps


class _V1Proxy:
    """Resolve symbols from v1 at call-time so tests can patch v1.*."""

    def __getattr__(self, name):
        import backend.server.routers.v1 as v1_mod
        return getattr(v1_mod, name)


v1 = _V1Proxy()
router = APIRouter()


########################################################
##################### Schedules ########################
########################################################


class ScheduleCreationRequest(pydantic.BaseModel):
    graph_version: Optional[int] = None
    name: str
    cron: str
    inputs: dict[str, Any]
    credentials: dict[str, CredentialsMetaInput] = pydantic.Field(default_factory=dict)
    timezone: Optional[str] = pydantic.Field(
        default=None,
        description="User's timezone for scheduling (e.g., 'America/New_York'). If not provided, will use user's saved timezone or UTC.",
    )


@router.post(
    path="/graphs/{graph_id}/schedules",
    summary="Create execution schedule",
    tags=["schedules"],
    dependencies=[Security(requires_user)],
)
async def create_graph_execution_schedule(
    user_id: Annotated[str, Security(get_user_id)],
    graph_id: str = Path(..., description="ID of the graph to schedule"),
    schedule_params: ScheduleCreationRequest = Body(),
) -> v1.scheduler.GraphExecutionJobInfo:
    graph = await v1.graph_db.get_graph(
        graph_id=graph_id,
        version=schedule_params.graph_version,
        user_id=user_id,
    )
    if not graph:
        raise HTTPException(
            status_code=404,
            detail=f"Graph #{graph_id} v{schedule_params.graph_version} not found.",
        )

    # Use timezone from request if provided, otherwise fetch from user profile
    if schedule_params.timezone:
        user_timezone = schedule_params.timezone
    else:
        user = await v1.get_user_by_id(user_id)
        user_timezone = v1.get_user_timezone_or_utc(user.timezone if user else None)

    result = await v1.get_scheduler_client().add_execution_schedule(
        user_id=user_id,
        graph_id=graph_id,
        graph_version=graph.version,
        name=schedule_params.name,
        cron=schedule_params.cron,
        input_data=schedule_params.inputs,
        input_credentials=schedule_params.credentials,
        user_timezone=user_timezone,
    )

    # Convert the next_run_time back to user timezone for display
    if result.next_run_time:
        result.next_run_time = v1.convert_utc_time_to_user_timezone(
            result.next_run_time, user_timezone
        )

    return result


@router.get(
    path="/graphs/{graph_id}/schedules",
    summary="List execution schedules for a graph",
    tags=["schedules"],
    dependencies=[Security(requires_user)],
)
async def list_graph_execution_schedules(
    user_id: Annotated[str, Security(get_user_id)],
    graph_id: str = Path(),
) -> list[v1.scheduler.GraphExecutionJobInfo]:
    return await v1.get_scheduler_client().get_execution_schedules(
        user_id=user_id,
        graph_id=graph_id,
    )


@router.get(
    path="/schedules",
    summary="List execution schedules for a user",
    tags=["schedules"],
    dependencies=[Security(requires_user)],
)
async def list_all_graphs_execution_schedules(
    user_id: Annotated[str, Security(get_user_id)],
) -> list[v1.scheduler.GraphExecutionJobInfo]:
    return await v1.get_scheduler_client().get_execution_schedules(user_id=user_id)


@router.delete(
    path="/schedules/{schedule_id}",
    summary="Delete execution schedule",
    tags=["schedules"],
    dependencies=[Security(requires_user)],
)
async def delete_graph_execution_schedule(
    user_id: Annotated[str, Security(get_user_id)],
    schedule_id: str = Path(..., description="ID of the schedule to delete"),
) -> dict[str, Any]:
    try:
        await v1.get_scheduler_client().delete_schedule(schedule_id, user_id=user_id)
    except NotFoundError:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Schedule #{schedule_id} not found",
        )
    return {"id": schedule_id}


########################################################
#####################  API KEY ##############################
########################################################


@router.post(
    "/api-keys",
    summary="Create new API key",
    tags=["api-keys"],
    dependencies=[Security(requires_user)],
)
async def create_api_key(
    request: CreateAPIKeyRequest, user_id: Annotated[str, Security(get_user_id)]
) -> CreateAPIKeyResponse:
    """Create a new API key"""
    api_key_info, plain_text_key = await v1.api_key_db.create_api_key(
        name=request.name,
        user_id=user_id,
        permissions=request.permissions,
        description=request.description,
    )
    return CreateAPIKeyResponse(api_key=api_key_info, plain_text_key=plain_text_key)


@router.get(
    "/api-keys",
    summary="List user API keys",
    tags=["api-keys"],
    dependencies=[Security(requires_user)],
)
async def get_api_keys(
    user_id: Annotated[str, Security(get_user_id)],
) -> list[v1.api_key_db.APIKeyInfo]:
    """List all API keys for the user"""
    return await v1.api_key_db.list_user_api_keys(user_id)


@router.get(
    "/api-keys/{key_id}",
    summary="Get specific API key",
    tags=["api-keys"],
    dependencies=[Security(requires_user)],
)
async def get_api_key(
    key_id: str, user_id: Annotated[str, Security(get_user_id)]
) -> v1.api_key_db.APIKeyInfo:
    """Get a specific API key"""
    api_key = await v1.api_key_db.get_api_key_by_id(key_id, user_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    return api_key


@router.delete(
    "/api-keys/{key_id}",
    summary="Revoke API key",
    tags=["api-keys"],
    dependencies=[Security(requires_user)],
)
async def delete_api_key(
    key_id: str, user_id: Annotated[str, Security(get_user_id)]
) -> v1.api_key_db.APIKeyInfo:
    """Revoke an API key"""
    return await v1.api_key_db.revoke_api_key(key_id, user_id)


@router.post(
    "/api-keys/{key_id}/suspend",
    summary="Suspend API key",
    tags=["api-keys"],
    dependencies=[Security(requires_user)],
)
async def suspend_key(
    key_id: str, user_id: Annotated[str, Security(get_user_id)]
) -> v1.api_key_db.APIKeyInfo:
    """Suspend an API key"""
    return await v1.api_key_db.suspend_api_key(key_id, user_id)


@router.put(
    "/api-keys/{key_id}/permissions",
    summary="Update key permissions",
    tags=["api-keys"],
    dependencies=[Security(requires_user)],
)
async def update_permissions(
    key_id: str,
    request: UpdatePermissionsRequest,
    user_id: Annotated[str, Security(get_user_id)],
) -> v1.api_key_db.APIKeyInfo:
    """Update API key permissions"""
    return await v1.api_key_db.update_api_key_permissions(
        key_id, user_id, request.permissions
    )
