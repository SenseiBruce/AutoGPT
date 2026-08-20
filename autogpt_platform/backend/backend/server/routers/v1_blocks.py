"""Blocks and upload routes."""

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
##################### Blocks ###########################
########################################################


def _compute_blocks_sync() -> str:
    """
    Synchronous function to compute blocks data.
    This does the heavy lifting: instantiate 226+ blocks, compute costs, serialize.
    """
    from backend.data.credit import get_block_cost

    block_classes = v1.get_blocks()
    result = []

    for block_class in block_classes.values():
        block_instance = block_class()
        if not block_instance.disabled:
            costs = get_block_cost(block_instance)
            # Convert BlockCost BaseModel objects to dictionaries for JSON serialization
            costs_dict = [
                cost.model_dump() if isinstance(cost, BaseModel) else cost
                for cost in costs
            ]
            result.append({**block_instance.to_dict(), "costs": costs_dict})

    # Use our JSON utility which properly handles complex types through to_dict conversion
    return dumps(result)


@cached(ttl_seconds=3600)
async def _get_cached_blocks() -> str:
    """
    Async cached function with thundering herd protection.
    On cache miss: runs heavy work in thread pool
    On cache hit: returns cached string immediately (no thread pool needed)
    """
    # Only run in thread pool on cache miss - cache hits return immediately
    return await run_in_threadpool(_compute_blocks_sync)


@router.get(
    path="/blocks",
    summary="List available blocks",
    tags=["blocks"],
    dependencies=[Security(requires_user)],
    responses={
        200: {
            "description": "Successful Response",
            "content": {
                "application/json": {
                    "schema": {
                        "items": {"additionalProperties": True, "type": "object"},
                        "type": "array",
                        "title": "Response Getv1List Available Blocks",
                    }
                }
            },
        }
    },
)
async def get_graph_blocks() -> Response:
    # Cache hit: returns immediately, Cache miss: runs in thread pool
    content = await _get_cached_blocks()
    return Response(
        content=content,
        media_type="application/json",
    )


@router.post(
    path="/blocks/{block_id}/execute",
    summary="Execute graph block",
    tags=["blocks"],
    dependencies=[Security(requires_user)],
)
async def execute_graph_block(
    block_id: str, data: BlockInput, user_id: Annotated[str, Security(get_user_id)]
) -> CompletedBlockOutput:
    obj = v1.get_block(block_id)
    if not obj:
        raise HTTPException(status_code=404, detail=f"Block #{block_id} not found.")

    # Get user context for block execution
    user = await v1.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user_context = UserContext(timezone=user.timezone)

    start_time = time.time()
    try:
        output = defaultdict(list)
        async for name, data in obj.execute(
            data,
            user_context=user_context,
            user_id=user_id,
            # Note: graph_exec_id and graph_id are not available for direct block execution
        ):
            output[name].append(data)

        # Record successful block execution with duration
        duration = time.time() - start_time
        block_type = obj.__class__.__name__
        v1.record_block_execution(
            block_type=block_type, status="success", duration=duration
        )

        return output
    except Exception:
        # Record failed block execution
        duration = time.time() - start_time
        block_type = obj.__class__.__name__
        v1.record_block_execution(block_type=block_type, status="error", duration=duration)
        raise


@router.post(
    path="/files/upload",
    summary="Upload file to cloud storage",
    tags=["files"],
    dependencies=[Security(requires_user)],
)
async def upload_file(
    user_id: Annotated[str, Security(get_user_id)],
    file: UploadFile = File(...),
    provider: str = "gcs",
    expiration_hours: int = 24,
) -> UploadFileResponse:
    """
    Upload a file to cloud storage and return a storage key that can be used
    with FileStoreBlock and AgentFileInputBlock.

    Args:
        file: The file to upload
        user_id: The user ID
        provider: Cloud storage provider ("gcs", "s3", "azure")
        expiration_hours: Hours until file expires (1-48)

    Returns:
        Dict containing the cloud storage path and signed URL
    """
    if expiration_hours < 1 or expiration_hours > 48:
        raise HTTPException(
            status_code=400, detail="Expiration hours must be between 1 and 48"
        )

    # Check file size limit before reading content to avoid memory issues
    max_size_mb = v1.settings.config.upload_file_size_limit_mb
    max_size_bytes = max_size_mb * 1024 * 1024

    # Try to get file size from headers first
    if hasattr(file, "size") and file.size is not None and file.size > max_size_bytes:
        raise v1._create_file_size_error(file.size, max_size_mb)

    # Read file content
    content = await file.read()
    content_size = len(content)

    # Double-check file size after reading (in case header was missing/incorrect)
    if content_size > max_size_bytes:
        raise v1._create_file_size_error(content_size, max_size_mb)

    # Extract common variables
    file_name = file.filename or "uploaded_file"
    content_type = file.content_type or "application/octet-stream"

    # Virus scan the content
    await v1.scan_content_safe(content, filename=file_name)

    # Check if cloud storage is configured
    cloud_storage = await v1.get_cloud_storage_handler()
    if not cloud_storage.config.gcs_bucket_name:
        # Fallback to base64 data URI when GCS is not configured
        base64_content = base64.b64encode(content).decode("utf-8")
        data_uri = f"data:{content_type};base64,{base64_content}"

        return UploadFileResponse(
            file_uri=data_uri,
            file_name=file_name,
            size=content_size,
            content_type=content_type,
            expires_in_hours=expiration_hours,
        )

    # Store in cloud storage
    storage_path = await cloud_storage.store_file(
        content=content,
        filename=file_name,
        provider=provider,
        expiration_hours=expiration_hours,
        user_id=user_id,
    )

    return UploadFileResponse(
        file_uri=storage_path,
        file_name=file_name,
        size=content_size,
        content_type=content_type,
        expires_in_hours=expiration_hours,
    )


