"""Graph and execution routes."""

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
from backend.util.run_status_filter import resolve_run_status_filter


class _V1Proxy:
    """Resolve symbols from v1 at call-time so tests can patch v1.*."""

    def __getattr__(self, name):
        import backend.server.routers.v1 as v1_mod
        return getattr(v1_mod, name)


v1 = _V1Proxy()
router = APIRouter()


########################################################
##################### Graphs ###########################
########################################################


class DeleteGraphResponse(TypedDict):
    version_counts: int


@router.get(
    path="/graphs",
    summary="List user graphs",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def list_graphs(
    user_id: Annotated[str, Security(get_user_id)],
) -> Sequence[v1.graph_db.GraphMeta]:
    paginated_result = await v1.graph_db.list_graphs_paginated(
        user_id=user_id,
        page=1,
        page_size=250,
        filter_by="active",
    )
    return paginated_result.graphs


@router.get(
    path="/graphs/{graph_id}",
    summary="Get specific graph",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
@router.get(
    path="/graphs/{graph_id}/versions/{version}",
    summary="Get graph version",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def get_graph(
    graph_id: str,
    user_id: Annotated[str, Security(get_user_id)],
    version: int | None = None,
    for_export: bool = False,
) -> v1.graph_db.GraphModel:
    graph = await v1.graph_db.get_graph(
        graph_id,
        version,
        user_id=user_id,
        for_export=for_export,
        include_subgraphs=True,  # needed to construct full credentials input schema
    )
    if not graph:
        raise HTTPException(status_code=404, detail=f"Graph #{graph_id} not found.")
    return graph


@router.get(
    path="/graphs/{graph_id}/versions",
    summary="Get all graph versions",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def get_graph_all_versions(
    graph_id: str, user_id: Annotated[str, Security(get_user_id)]
) -> Sequence[v1.graph_db.GraphModel]:
    graphs = await v1.graph_db.get_graph_all_versions(graph_id, user_id=user_id)
    if not graphs:
        raise HTTPException(status_code=404, detail=f"Graph #{graph_id} not found.")
    return graphs


@router.post(
    path="/graphs",
    summary="Create new graph",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def create_new_graph(
    create_graph: CreateGraph,
    user_id: Annotated[str, Security(get_user_id)],
) -> v1.graph_db.GraphModel:
    graph = v1.graph_db.make_graph_model(create_graph.graph, user_id)
    graph.reassign_ids(user_id=user_id, reassign_graph_id=True)
    graph.validate_graph(for_run=False)

    # The return value of the create graph & library function is intentionally not used here,
    # as the graph already valid and no sub-graphs are returned back.
    await v1.graph_db.create_graph(graph, user_id=user_id)
    await v1.library_db.create_library_agent(graph, user_id=user_id)
    return await v1.on_graph_activate(graph, user_id=user_id)


@router.delete(
    path="/graphs/{graph_id}",
    summary="Delete graph permanently",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def delete_graph(
    graph_id: str, user_id: Annotated[str, Security(get_user_id)]
) -> DeleteGraphResponse:
    if active_version := await v1.graph_db.get_graph(graph_id, user_id=user_id):
        await v1.on_graph_deactivate(active_version, user_id=user_id)

    return {"version_counts": await v1.graph_db.delete_graph(graph_id, user_id=user_id)}


@router.put(
    path="/graphs/{graph_id}",
    summary="Update graph version",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def update_graph(
    graph_id: str,
    graph: v1.graph_db.Graph,
    user_id: Annotated[str, Security(get_user_id)],
) -> v1.graph_db.GraphModel:
    # Sanity check
    if graph.id and graph.id != graph_id:
        raise HTTPException(400, detail="Graph ID does not match ID in URI")

    # Determine new version
    existing_versions = await v1.graph_db.get_graph_all_versions(graph_id, user_id=user_id)
    if not existing_versions:
        raise HTTPException(404, detail=f"Graph #{graph_id} not found")
    latest_version_number = max(g.version for g in existing_versions)
    graph.version = latest_version_number + 1

    current_active_version = next((v for v in existing_versions if v.is_active), None)
    graph = v1.graph_db.make_graph_model(graph, user_id)
    graph.reassign_ids(user_id=user_id, reassign_graph_id=False)
    graph.validate_graph(for_run=False)

    new_graph_version = await v1.graph_db.create_graph(graph, user_id=user_id)

    if new_graph_version.is_active:
        # Keep the library agent up to date with the new active version
        await v1.library_db.update_agent_version_in_library(
            user_id, graph.id, graph.version
        )

        # Handle activation of the new graph first to ensure continuity
        new_graph_version = await v1.on_graph_activate(new_graph_version, user_id=user_id)
        # Ensure new version is the only active version
        await v1.graph_db.set_graph_active_version(
            graph_id=graph_id, version=new_graph_version.version, user_id=user_id
        )
        if current_active_version:
            # Handle deactivation of the previously active version
            await v1.on_graph_deactivate(current_active_version, user_id=user_id)

    # Fetch new graph version *with sub-graphs* (needed for credentials input schema)
    new_graph_version_with_subgraphs = await v1.graph_db.get_graph(
        graph_id,
        new_graph_version.version,
        user_id=user_id,
        include_subgraphs=True,
    )
    assert new_graph_version_with_subgraphs  # make type checker happy
    return new_graph_version_with_subgraphs


@router.put(
    path="/graphs/{graph_id}/versions/active",
    summary="Set active graph version",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def set_graph_active_version(
    graph_id: str,
    request_body: SetGraphActiveVersion,
    user_id: Annotated[str, Security(get_user_id)],
):
    new_active_version = request_body.active_graph_version
    new_active_graph = await v1.graph_db.get_graph(
        graph_id, new_active_version, user_id=user_id
    )
    if not new_active_graph:
        raise HTTPException(404, f"Graph #{graph_id} v{new_active_version} not found")

    current_active_graph = await v1.graph_db.get_graph(graph_id, user_id=user_id)

    # Handle activation of the new graph first to ensure continuity
    await v1.on_graph_activate(new_active_graph, user_id=user_id)
    # Ensure new version is the only active version
    await v1.graph_db.set_graph_active_version(
        graph_id=graph_id,
        version=new_active_version,
        user_id=user_id,
    )

    # Keep the library agent up to date with the new active version
    await v1.library_db.update_agent_version_in_library(
        user_id, new_active_graph.id, new_active_graph.version
    )

    if current_active_graph and current_active_graph.version != new_active_version:
        # Handle deactivation of the previously active version
        await v1.on_graph_deactivate(current_active_graph, user_id=user_id)


@router.post(
    path="/graphs/{graph_id}/execute/{graph_version}",
    summary="Execute graph agent",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def execute_graph(
    graph_id: str,
    user_id: Annotated[str, Security(get_user_id)],
    inputs: Annotated[dict[str, Any], Body(..., embed=True, default_factory=dict)],
    credentials_inputs: Annotated[
        dict[str, CredentialsMetaInput], Body(..., embed=True, default_factory=dict)
    ],
    graph_version: Optional[int] = None,
    preset_id: Optional[str] = None,
) -> v1.execution_db.GraphExecutionMeta:
    user_credit_model = await v1.get_user_credit_model(user_id)
    current_balance = await user_credit_model.get_credits(user_id)
    if current_balance <= 0:
        raise HTTPException(
            status_code=402,
            detail="Insufficient balance to execute the agent. Please top up your account.",
        )

    try:
        result = await v1.execution_utils.add_graph_execution(
            graph_id=graph_id,
            user_id=user_id,
            inputs=inputs,
            preset_id=preset_id,
            graph_version=graph_version,
            graph_credentials_inputs=credentials_inputs,
        )
        # Record successful graph execution
        v1.record_graph_execution(graph_id=graph_id, status="success", user_id=user_id)
        v1.record_graph_operation(operation="execute", status="success")
        return result
    except GraphValidationError as e:
        # Record failed graph execution
        v1.record_graph_execution(
            graph_id=graph_id, status="validation_error", user_id=user_id
        )
        v1.record_graph_operation(operation="execute", status="validation_error")
        # Return structured validation errors that the frontend can parse
        raise HTTPException(
            status_code=400,
            detail={
                "type": "validation_error",
                "message": e.message,
                # TODO: only return node-specific errors if user has access to graph
                "node_errors": e.node_errors,
            },
        )
    except Exception:
        # Record any other failures
        v1.record_graph_execution(graph_id=graph_id, status="error", user_id=user_id)
        v1.record_graph_operation(operation="execute", status="error")
        raise


@router.post(
    path="/graphs/{graph_id}/executions/{graph_exec_id}/stop",
    summary="Stop graph execution",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def stop_graph_run(
    graph_id: str, graph_exec_id: str, user_id: Annotated[str, Security(get_user_id)]
) -> v1.execution_db.GraphExecutionMeta | None:
    res = await _stop_graph_run(
        user_id=user_id,
        graph_id=graph_id,
        graph_exec_id=graph_exec_id,
    )
    if not res:
        return None
    return res[0]


async def _stop_graph_run(
    user_id: str,
    graph_id: Optional[str] = None,
    graph_exec_id: Optional[str] = None,
) -> list[v1.execution_db.GraphExecutionMeta]:
    graph_execs = await v1.execution_db.get_graph_executions(
        user_id=user_id,
        graph_id=graph_id,
        graph_exec_id=graph_exec_id,
        statuses=[
            v1.execution_db.ExecutionStatus.INCOMPLETE,
            v1.execution_db.ExecutionStatus.QUEUED,
            v1.execution_db.ExecutionStatus.RUNNING,
        ],
    )
    stopped_execs = [
        v1.execution_utils.stop_graph_execution(graph_exec_id=exec.id, user_id=user_id)
        for exec in graph_execs
    ]
    await asyncio.gather(*stopped_execs)
    return graph_execs


@router.get(
    path="/executions",
    summary="List all executions",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def list_graphs_executions(
    user_id: Annotated[str, Security(get_user_id)],
) -> list[v1.execution_db.GraphExecutionMeta]:
    paginated_result = await v1.execution_db.get_graph_executions_paginated(
        user_id=user_id,
        page=1,
        page_size=250,
    )
    return paginated_result.executions


@router.get(
    path="/graphs/{graph_id}/executions",
    summary="List graph executions",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def list_graph_executions(
    graph_id: str,
    user_id: Annotated[str, Security(get_user_id)],
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        25, ge=1, le=100, description="Number of executions per page"
    ),
    status_group: Optional[str] = Query(
        None,
        description="Preset filter: failed, running, completed, or all",
    ),
    statuses: Optional[list[str]] = Query(
        None,
        description=(
            "Filter by execution status "
            "(QUEUED, RUNNING, COMPLETED, FAILED, TERMINATED, INCOMPLETE)"
        ),
    ),
) -> v1.execution_db.GraphExecutionsPaginated:
    status_values = resolve_run_status_filter(
        status_group=status_group, statuses=statuses
    )
    parsed_statuses = (
        [v1.execution_db.ExecutionStatus(value) for value in status_values]
        if status_values
        else None
    )
    return await v1.execution_db.get_graph_executions_paginated(
        graph_id=graph_id,
        user_id=user_id,
        page=page,
        page_size=page_size,
        statuses=parsed_statuses,
    )


@router.get(
    path="/graphs/{graph_id}/executions/{graph_exec_id}",
    summary="Get execution details",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
)
async def get_graph_execution(
    graph_id: str,
    graph_exec_id: str,
    user_id: Annotated[str, Security(get_user_id)],
) -> v1.execution_db.GraphExecution | v1.execution_db.GraphExecutionWithNodes:
    graph = await v1.graph_db.get_graph(graph_id=graph_id, user_id=user_id)
    if not graph:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND, detail=f"Graph #{graph_id} not found"
        )

    result = await v1.execution_db.get_graph_execution(
        user_id=user_id,
        execution_id=graph_exec_id,
        include_node_executions=graph.user_id == user_id,
    )
    if not result or result.graph_id != graph_id:
        raise HTTPException(
            status_code=404, detail=f"Graph execution #{graph_exec_id} not found."
        )

    return result


@router.delete(
    path="/executions/{graph_exec_id}",
    summary="Delete graph execution",
    tags=["graphs"],
    dependencies=[Security(requires_user)],
    status_code=HTTP_204_NO_CONTENT,
)
async def delete_graph_execution(
    graph_exec_id: str,
    user_id: Annotated[str, Security(get_user_id)],
) -> None:
    await v1.execution_db.delete_graph_execution(
        graph_exec_id=graph_exec_id, user_id=user_id
    )


class ShareRequest(pydantic.BaseModel):
    """Optional request body for share endpoint."""

    pass  # Empty body is fine


class ShareResponse(pydantic.BaseModel):
    """Response from share endpoints."""

    share_url: str
    share_token: str


@router.post(
    "/graphs/{graph_id}/executions/{graph_exec_id}/share",
    dependencies=[Security(requires_user)],
)
async def enable_execution_sharing(
    graph_id: Annotated[str, Path],
    graph_exec_id: Annotated[str, Path],
    user_id: Annotated[str, Security(get_user_id)],
    _body: ShareRequest = Body(default=ShareRequest()),
) -> ShareResponse:
    """Enable sharing for a graph execution."""
    # Verify the execution belongs to the user
    execution = await v1.execution_db.get_graph_execution(
        user_id=user_id, execution_id=graph_exec_id
    )
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Generate a unique share token
    share_token = str(uuid.uuid4())

    # Update the execution with share info
    await v1.execution_db.update_graph_execution_share_status(
        execution_id=graph_exec_id,
        user_id=user_id,
        is_shared=True,
        share_token=share_token,
        shared_at=datetime.now(timezone.utc),
    )

    # Return the share URL
    frontend_url = Settings().config.frontend_base_url or "http://localhost:3000"
    share_url = f"{frontend_url}/share/{share_token}"

    return ShareResponse(share_url=share_url, share_token=share_token)


@router.delete(
    "/graphs/{graph_id}/executions/{graph_exec_id}/share",
    status_code=HTTP_204_NO_CONTENT,
    dependencies=[Security(requires_user)],
)
async def disable_execution_sharing(
    graph_id: Annotated[str, Path],
    graph_exec_id: Annotated[str, Path],
    user_id: Annotated[str, Security(get_user_id)],
) -> None:
    """Disable sharing for a graph execution."""
    # Verify the execution belongs to the user
    execution = await v1.execution_db.get_graph_execution(
        user_id=user_id, execution_id=graph_exec_id
    )
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Remove share info
    await v1.execution_db.update_graph_execution_share_status(
        execution_id=graph_exec_id,
        user_id=user_id,
        is_shared=False,
        share_token=None,
        shared_at=None,
    )


@router.get("/public/shared/{share_token}")
async def get_shared_execution(
    share_token: Annotated[
        str,
        Path(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
    ],
) -> v1.execution_db.SharedExecutionResponse:
    """Get a shared graph execution by share token (no auth required)."""
    execution = await v1.execution_db.get_graph_execution_by_share_token(share_token)
    if not execution:
        raise HTTPException(status_code=404, detail="Shared execution not found")

    return execution


