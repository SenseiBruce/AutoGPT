"""Credits and billing routes."""

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
##################### Credits ##########################
########################################################


@router.get(
    path="/credits",
    tags=["credits"],
    summary="Get user credits",
    dependencies=[Security(requires_user)],
)
async def get_user_credits(
    user_id: Annotated[str, Security(get_user_id)],
) -> dict[str, int]:
    user_credit_model = await v1.get_user_credit_model(user_id)
    return {"credits": await user_credit_model.get_credits(user_id)}


@router.post(
    path="/credits",
    summary="Request credit top up",
    tags=["credits"],
    dependencies=[Security(requires_user)],
)
async def request_top_up(
    request: RequestTopUp, user_id: Annotated[str, Security(get_user_id)]
):
    user_credit_model = await v1.get_user_credit_model(user_id)
    checkout_url = await user_credit_model.top_up_intent(user_id, request.credit_amount)
    return {"checkout_url": checkout_url}


@router.post(
    path="/credits/{transaction_key}/refund",
    summary="Refund credit transaction",
    tags=["credits"],
    dependencies=[Security(requires_user)],
)
async def refund_top_up(
    user_id: Annotated[str, Security(get_user_id)],
    transaction_key: str,
    metadata: dict[str, str],
) -> int:
    user_credit_model = await v1.get_user_credit_model(user_id)
    return await user_credit_model.top_up_refund(user_id, transaction_key, metadata)


@router.patch(
    path="/credits",
    summary="Fulfill checkout session",
    tags=["credits"],
    dependencies=[Security(requires_user)],
)
async def fulfill_checkout(user_id: Annotated[str, Security(get_user_id)]):
    user_credit_model = await v1.get_user_credit_model(user_id)
    await user_credit_model.fulfill_checkout(user_id=user_id)
    return Response(status_code=200)


@router.post(
    path="/credits/auto-top-up",
    summary="Configure auto top up",
    tags=["credits"],
    dependencies=[Security(requires_user)],
)
async def configure_user_auto_top_up(
    request: AutoTopUpConfig, user_id: Annotated[str, Security(get_user_id)]
) -> str:
    if request.threshold < 0:
        raise HTTPException(status_code=422, detail="Threshold must be greater than 0")
    if request.amount < 500 and request.amount != 0:
        raise HTTPException(
            status_code=422, detail="Amount must be greater than or equal to 500"
        )
    if request.amount != 0 and request.amount < request.threshold:
        raise HTTPException(
            status_code=422, detail="Amount must be greater than or equal to threshold"
        )

    user_credit_model = await v1.get_user_credit_model(user_id)
    current_balance = await user_credit_model.get_credits(user_id)

    if current_balance < request.threshold:
        await user_credit_model.top_up_credits(user_id, request.amount)
    else:
        await user_credit_model.top_up_credits(user_id, 0)

    await v1.set_auto_top_up(
        user_id, AutoTopUpConfig(threshold=request.threshold, amount=request.amount)
    )
    return "Auto top-up settings updated"


@router.get(
    path="/credits/auto-top-up",
    summary="Get auto top up",
    tags=["credits"],
    dependencies=[Security(requires_user)],
)
async def get_user_auto_top_up(
    user_id: Annotated[str, Security(get_user_id)],
) -> AutoTopUpConfig:
    return await v1.get_auto_top_up(user_id)


@router.post(
    path="/credits/stripe_webhook", summary="Handle Stripe webhooks", tags=["credits"]
)
async def stripe_webhook(request: Request):
    # Get the raw request body
    payload = await request.body()
    # Get the signature header
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, v1.settings.secrets.stripe_webhook_secret
        )
    except ValueError as e:
        # Invalid payload
        raise HTTPException(
            status_code=400, detail=f"Invalid payload: {str(e) or type(e).__name__}"
        )
    except stripe.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(
            status_code=400, detail=f"Invalid signature: {str(e) or type(e).__name__}"
        )

    if (
        event["type"] == "checkout.session.completed"
        or event["type"] == "checkout.session.async_payment_succeeded"
    ):
        await UserCredit().fulfill_checkout(session_id=event["data"]["object"]["id"])

    if event["type"] == "charge.dispute.created":
        await UserCredit().handle_dispute(event["data"]["object"])

    if event["type"] == "refund.created" or event["type"] == "charge.dispute.closed":
        await UserCredit().deduct_credits(event["data"]["object"])

    return Response(status_code=200)


@router.get(
    path="/credits/manage",
    tags=["credits"],
    summary="Manage payment methods",
    dependencies=[Security(requires_user)],
)
async def manage_payment_method(
    user_id: Annotated[str, Security(get_user_id)],
) -> dict[str, str]:
    user_credit_model = await v1.get_user_credit_model(user_id)
    return {"url": await user_credit_model.create_billing_portal_session(user_id)}


@router.get(
    path="/credits/transactions",
    tags=["credits"],
    summary="Get credit history",
    dependencies=[Security(requires_user)],
)
async def get_credit_history(
    user_id: Annotated[str, Security(get_user_id)],
    transaction_time: datetime | None = None,
    transaction_type: str | None = None,
    transaction_count_limit: int = 100,
) -> TransactionHistory:
    if transaction_count_limit < 1 or transaction_count_limit > 1000:
        raise ValueError("Transaction count limit must be between 1 and 1000")

    user_credit_model = await v1.get_user_credit_model(user_id)
    return await user_credit_model.get_transaction_history(
        user_id=user_id,
        transaction_time_ceiling=transaction_time,
        transaction_count_limit=transaction_count_limit,
        transaction_type=transaction_type,
    )


@router.get(
    path="/credits/refunds",
    tags=["credits"],
    summary="Get refund requests",
    dependencies=[Security(requires_user)],
)
async def get_refund_requests(
    user_id: Annotated[str, Security(get_user_id)],
) -> list[RefundRequest]:
    user_credit_model = await v1.get_user_credit_model(user_id)
    return await user_credit_model.get_refund_requests(user_id)


