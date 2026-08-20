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

import backend.server.integrations.router
import backend.server.routers.analytics
import backend.server.v2.library.db as library_db
from backend.data import api_key as api_key_db
from backend.data import execution as execution_db
from backend.data import graph as graph_db
from backend.data.block import BlockInput, CompletedBlockOutput, get_block, get_blocks
from backend.data.credit import (
    AutoTopUpConfig,
    RefundRequest,
    TransactionHistory,
    UserCredit,
    get_auto_top_up,
    get_user_credit_model,
    set_auto_top_up,
)
from backend.data.execution import UserContext
from backend.data.model import CredentialsMetaInput
from backend.data.notifications import NotificationPreference, NotificationPreferenceDTO
from backend.data.onboarding import (
    UserOnboardingUpdate,
    get_recommended_agents,
    get_user_onboarding,
    onboarding_enabled,
    reset_user_onboarding,
    update_user_onboarding,
)
from backend.data.user import (
    get_or_create_user,
    get_user_by_id,
    get_user_notification_preference,
    update_user_email,
    update_user_notification_preference,
    update_user_timezone,
)
from backend.executor import scheduler
from backend.executor import utils as execution_utils
from backend.integrations.webhooks.graph_lifecycle_hooks import (
    on_graph_activate,
    on_graph_deactivate,
)
from backend.monitoring.instrumentation import (
    record_block_execution,
    record_graph_execution,
    record_graph_operation,
)
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
from backend.util.clients import get_scheduler_client
from backend.util.cloud_storage import get_cloud_storage_handler
from backend.util.exceptions import GraphValidationError, NotFoundError
from backend.util.json import dumps
from backend.util.settings import Settings
from backend.util.timezone_utils import (
    convert_utc_time_to_user_timezone,
    get_user_timezone_or_utc,
)
from backend.util.virus_scanner import scan_content_safe


def _create_file_size_error(size_bytes: int, max_size_mb: int) -> HTTPException:
    """Create standardized file size error response."""
    return HTTPException(
        status_code=400,
        detail=f"File size ({size_bytes} bytes) exceeds the maximum allowed size of {max_size_mb}MB",
    )


settings = Settings()
logger = logging.getLogger(__name__)

# Define the API routes
v1_router = APIRouter()

v1_router.include_router(
    backend.server.integrations.router.router,
    prefix="/integrations",
    tags=["integrations"],
)

v1_router.include_router(
    backend.server.routers.analytics.router,
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Security(requires_user)],
)

from .v1_auth import router as v1_auth_router
v1_router.include_router(v1_auth_router)
from .v1_blocks import router as v1_blocks_router
v1_router.include_router(v1_blocks_router)
from .v1_credits import router as v1_credits_router
v1_router.include_router(v1_credits_router)
from .v1_graphs import router as v1_graphs_router
v1_router.include_router(v1_graphs_router)
from .v1_schedules import router as v1_schedules_router
v1_router.include_router(v1_schedules_router)

from .v1_auth import get_or_create_user_route
from .v1_auth import update_user_email_route
from .v1_auth import get_user_timezone_route
from .v1_auth import update_user_timezone_route
from .v1_auth import get_preferences
from .v1_auth import update_preferences
from .v1_auth import get_onboarding
from .v1_auth import update_onboarding
from .v1_auth import get_onboarding_agents
from .v1_auth import is_onboarding_enabled
from .v1_auth import reset_onboarding
from .v1_blocks import _compute_blocks_sync
from .v1_blocks import _get_cached_blocks
from .v1_blocks import get_graph_blocks
from .v1_blocks import execute_graph_block
from .v1_blocks import upload_file
from .v1_credits import get_user_credits
from .v1_credits import request_top_up
from .v1_credits import refund_top_up
from .v1_credits import fulfill_checkout
from .v1_credits import configure_user_auto_top_up
from .v1_credits import get_user_auto_top_up
from .v1_credits import stripe_webhook
from .v1_credits import manage_payment_method
from .v1_credits import get_credit_history
from .v1_credits import get_refund_requests
from .v1_graphs import DeleteGraphResponse
from .v1_graphs import list_graphs
from .v1_graphs import get_graph
from .v1_graphs import get_graph_all_versions
from .v1_graphs import create_new_graph
from .v1_graphs import delete_graph
from .v1_graphs import update_graph
from .v1_graphs import set_graph_active_version
from .v1_graphs import execute_graph
from .v1_graphs import stop_graph_run
from .v1_graphs import _stop_graph_run
from .v1_graphs import list_graphs_executions
from .v1_graphs import list_graph_executions
from .v1_graphs import get_graph_execution
from .v1_graphs import delete_graph_execution
from .v1_graphs import ShareRequest
from .v1_graphs import ShareResponse
from .v1_graphs import enable_execution_sharing
from .v1_graphs import disable_execution_sharing
from .v1_graphs import get_shared_execution
from .v1_schedules import ScheduleCreationRequest
from .v1_schedules import create_graph_execution_schedule
from .v1_schedules import list_graph_execution_schedules
from .v1_schedules import list_all_graphs_execution_schedules
from .v1_schedules import delete_graph_execution_schedule
from .v1_schedules import create_api_key
from .v1_schedules import get_api_keys
from .v1_schedules import get_api_key
from .v1_schedules import delete_api_key
from .v1_schedules import suspend_key
from .v1_schedules import update_permissions
