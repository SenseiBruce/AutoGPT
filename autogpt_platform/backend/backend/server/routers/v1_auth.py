"""Auth and onboarding routes."""

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
##################### Auth #############################
########################################################


@router.post(
    "/auth/user",
    summary="Get or create user",
    tags=["auth"],
    dependencies=[Security(requires_user)],
)
async def get_or_create_user_route(user_data: dict = Security(get_jwt_payload)):
    user = await v1.get_or_create_user(user_data)
    return user.model_dump()


@router.post(
    "/auth/user/email",
    summary="Update user email",
    tags=["auth"],
    dependencies=[Security(requires_user)],
)
async def update_user_email_route(
    user_id: Annotated[str, Security(get_user_id)], email: str = Body(...)
) -> dict[str, str]:
    await v1.update_user_email(user_id, email)

    return {"email": email}


@router.get(
    "/auth/user/timezone",
    summary="Get user timezone",
    tags=["auth"],
    dependencies=[Security(requires_user)],
)
async def get_user_timezone_route(
    user_data: dict = Security(get_jwt_payload),
) -> TimezoneResponse:
    """Get user timezone setting."""
    user = await v1.get_or_create_user(user_data)
    return TimezoneResponse(timezone=user.timezone)


@router.post(
    "/auth/user/timezone",
    summary="Update user timezone",
    tags=["auth"],
    dependencies=[Security(requires_user)],
)
async def update_user_timezone_route(
    user_id: Annotated[str, Security(get_user_id)], request: UpdateTimezoneRequest
) -> TimezoneResponse:
    """Update user timezone. The timezone should be a valid IANA timezone identifier."""
    user = await v1.update_user_timezone(user_id, str(request.timezone))
    return TimezoneResponse(timezone=user.timezone)


@router.get(
    "/auth/user/preferences",
    summary="Get notification preferences",
    tags=["auth"],
    dependencies=[Security(requires_user)],
)
async def get_preferences(
    user_id: Annotated[str, Security(get_user_id)],
) -> NotificationPreference:
    preferences = await v1.get_user_notification_preference(user_id)
    return preferences


@router.post(
    "/auth/user/preferences",
    summary="Update notification preferences",
    tags=["auth"],
    dependencies=[Security(requires_user)],
)
async def update_preferences(
    user_id: Annotated[str, Security(get_user_id)],
    preferences: NotificationPreferenceDTO = Body(...),
) -> NotificationPreference:
    output = await v1.update_user_notification_preference(user_id, preferences)
    return output


########################################################
##################### Onboarding #######################
########################################################


@router.get(
    "/onboarding",
    summary="Get onboarding status",
    tags=["onboarding"],
    dependencies=[Security(requires_user)],
)
async def get_onboarding(user_id: Annotated[str, Security(get_user_id)]):
    return await v1.get_user_onboarding(user_id)


@router.patch(
    "/onboarding",
    summary="Update onboarding progress",
    tags=["onboarding"],
    dependencies=[Security(requires_user)],
)
async def update_onboarding(
    user_id: Annotated[str, Security(get_user_id)], data: UserOnboardingUpdate
):
    return await v1.update_user_onboarding(user_id, data)


@router.get(
    "/onboarding/agents",
    summary="Get recommended agents",
    tags=["onboarding"],
    dependencies=[Security(requires_user)],
)
async def get_onboarding_agents(
    user_id: Annotated[str, Security(get_user_id)],
):
    return await v1.get_recommended_agents(user_id)


@router.get(
    "/onboarding/enabled",
    summary="Check onboarding enabled",
    tags=["onboarding", "public"],
    dependencies=[Security(requires_user)],
)
async def is_onboarding_enabled():
    return await v1.onboarding_enabled()


@router.post(
    "/onboarding/reset",
    summary="Reset onboarding progress",
    tags=["onboarding"],
    dependencies=[Security(requires_user)],
)
async def reset_onboarding(user_id: Annotated[str, Security(get_user_id)]):
    return await v1.reset_user_onboarding(user_id)


