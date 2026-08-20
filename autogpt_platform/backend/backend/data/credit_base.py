"""Credit base types and abstract user credit interface."""

import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

import stripe
from prisma.enums import (
    CreditRefundRequestStatus,
    CreditTransactionType,
    NotificationType,
    OnboardingStep,
)
from prisma.errors import UniqueViolationError
from prisma.models import CreditRefundRequest, CreditTransaction, User, UserBalance
from prisma.types import CreditRefundRequestCreateInput, CreditTransactionWhereInput
from pydantic import BaseModel

from backend.data.block_cost_config import BLOCK_COSTS
from backend.data.db import query_raw_with_schema
from backend.data.includes import MAX_CREDIT_REFUND_REQUESTS_FETCH
from backend.data.model import (
    AutoTopUpConfig,
    RefundRequest,
    TopUpType,
    TransactionHistory,
    UserTransaction,
)
from backend.data.notifications import NotificationEventModel, RefundRequestData
from backend.data.user import get_user_by_id, get_user_email_by_id
from backend.notifications.notifications import queue_notification_async
from backend.server.v2.admin.model import UserHistoryResponse
from backend.util.exceptions import InsufficientBalanceError
from backend.util.feature_flag import Flag, is_feature_enabled
from backend.util.json import SafeJson, dumps
from backend.util.models import Pagination
from backend.util.retry import func_retry
from backend.util.settings import Settings

if TYPE_CHECKING:
    from backend.data.block import Block, BlockCost

settings = Settings()
stripe.api_key = settings.secrets.stripe_api_key
logger = logging.getLogger(__name__)
base_url = settings.config.frontend_base_url or settings.config.platform_base_url

# Constants for test compatibility
POSTGRES_INT_MAX = 2147483647
POSTGRES_INT_MIN = -2147483648


class UsageTransactionMetadata(BaseModel):
    graph_exec_id: str | None = None
    graph_id: str | None = None
    node_id: str | None = None
    node_exec_id: str | None = None
    block_id: str | None = None
    block: str | None = None
    input: dict[str, Any] | None = None
    reason: str | None = None


class UserCreditBase(ABC):
    @abstractmethod
    async def get_credits(self, user_id: str) -> int:
        """
        Get the current credits for the user.

        Returns:
            int: The current credits for the user.
        """
        pass

    @abstractmethod
    async def get_transaction_history(
        self,
        user_id: str,
        transaction_count_limit: int,
        transaction_time_ceiling: datetime | None = None,
        transaction_type: str | None = None,
    ) -> TransactionHistory:
        """
        Get the credit transactions for the user.

        Args:
            user_id (str): The user ID.
            transaction_count_limit (int): The transaction count limit.
            transaction_time_ceiling (datetime): The upper bound of the transaction time.
            transaction_type (str): The transaction type filter.

        Returns:
            TransactionHistory: The credit transactions for the user.
        """
        pass

    @abstractmethod
    async def get_refund_requests(self, user_id: str) -> list[RefundRequest]:
        """
        Get the refund requests for the user.

        Args:
            user_id (str): The user ID.

        Returns:
            list[RefundRequest]: The refund requests for the user.
        """
        pass

    @abstractmethod
    async def spend_credits(
        self,
        user_id: str,
        cost: int,
        metadata: UsageTransactionMetadata,
    ) -> int:
        """
        Spend the credits for the user based on the cost.

        Args:
            user_id (str): The user ID.
            cost (int): The cost to spend.
            metadata (UsageTransactionMetadata): The metadata of the transaction.

        Returns:
            int: The remaining balance.
        """
        pass

    @abstractmethod
    async def top_up_credits(self, user_id: str, amount: int):
        """
        Top up the credits for the user.

        Args:
            user_id (str): The user ID.
            amount (int): The amount to top up.
        """
        pass

    @abstractmethod
    async def onboarding_reward(
        self, user_id: str, credits: int, step: OnboardingStep
    ) -> bool:
        """
        Reward the user with credits for completing an onboarding step.
        Won't reward if the user has already received credits for the step.

        Args:
            user_id (str): The user ID.
            credits (int): The amount to reward.
            step (OnboardingStep): The onboarding step.

        Returns:
            bool: True if rewarded, False if already rewarded.
        """
        pass

    @abstractmethod
    async def top_up_intent(self, user_id: str, amount: int) -> str:
        """
        Create a payment intent to top up the credits for the user.

        Args:
            user_id (str): The user ID.
            amount (int): The amount of credits to top up.

        Returns:
            str: The redirect url to the payment page.
        """
        pass

    @abstractmethod
    async def top_up_refund(
        self, user_id: str, transaction_key: str, metadata: dict[str, str]
    ) -> int:
        """
        Refund the top-up transaction for the user.

        Args:
            user_id (str): The user ID.
            transaction_key (str): The top-up transaction key to refund.
            metadata (dict[str, str]): The metadata of the refund.

        Returns:
            int: The amount refunded.
        """
        pass

    @abstractmethod
    async def deduct_credits(
        self,
        request: stripe.Refund | stripe.Dispute,
    ):
        """
        Deduct the credits for the user based on the dispute or refund of the top-up.

        Args:
            request (stripe.Refund | stripe.Dispute): The refund or dispute request.
        """
        pass

    @abstractmethod
    async def handle_dispute(self, dispute: stripe.Dispute):
        """
        Handle the dispute for the user based on the dispute request.

        Args:
            dispute (stripe.Dispute): The dispute request.
        """
        pass

    @abstractmethod
    async def fulfill_checkout(
        self, *, session_id: str | None = None, user_id: str | None = None
    ):
        """
        Fulfill the Stripe checkout session.

        Args:
            session_id (str | None): The checkout session ID. Will try to fulfill most recent if None.
            user_id (str | None): The user ID must be provided if session_id is None.
        """
        pass

    @staticmethod
    async def create_billing_portal_session(user_id: str) -> str:
        session = stripe.billing_portal.Session.create(
            customer=await get_stripe_customer_id(user_id),
            return_url=base_url + "/profile/credits",
        )
        return session.url

    @staticmethod
    def time_now() -> datetime:
        return datetime.now(timezone.utc)

    # ====== Transaction Helper Methods ====== #
    # Any modifications to the transaction table should only be done through these methods #

    async def _get_credits(self, user_id: str) -> tuple[int, datetime]:
        """
        Returns the current balance of the user & the latest balance snapshot time.
        """
        # Check UserBalance first for efficiency and consistency
        user_balance = await UserBalance.prisma().find_unique(where={"userId": user_id})
        if user_balance:
            return user_balance.balance, user_balance.updatedAt

        # Fallback to transaction history computation if UserBalance doesn't exist
        top_time = self.time_now()
        snapshot = await CreditTransaction.prisma().find_first(
            where={
                "userId": user_id,
                "createdAt": {"lte": top_time},
                "isActive": True,
                "NOT": [{"runningBalance": None}],
            },
            order={"createdAt": "desc"},
        )
        datetime_min = datetime.min.replace(tzinfo=timezone.utc)
        snapshot_balance = snapshot.runningBalance or 0 if snapshot else 0
        snapshot_time = snapshot.createdAt if snapshot else datetime_min

        return snapshot_balance, snapshot_time

    @func_retry
    async def _enable_transaction(
        self,
        transaction_key: str,
        user_id: str,
        metadata: SafeJson,
        new_transaction_key: str | None = None,
    ):
        # First check if transaction exists and is inactive (safety check)
        transaction = await CreditTransaction.prisma().find_first(
            where={
                "transactionKey": transaction_key,
                "userId": user_id,
                "isActive": False,
            }
        )
        if not transaction:
            # Transaction doesn't exist or is already active, return early
            return None

        # Atomic operation to enable transaction and update user balance using UserBalance
        result = await query_raw_with_schema(
            """
            WITH user_balance_lock AS (
                SELECT 
                    $2::text as userId, 
                    COALESCE(
                        (SELECT balance FROM {schema_prefix}"UserBalance" WHERE "userId" = $2 FOR UPDATE),
                        -- Fallback: compute balance from transaction history if UserBalance doesn't exist
                        (SELECT COALESCE(ct."runningBalance", 0) 
                         FROM {schema_prefix}"CreditTransaction" ct 
                         WHERE ct."userId" = $2 
                           AND ct."isActive" = true 
                           AND ct."runningBalance" IS NOT NULL 
                         ORDER BY ct."createdAt" DESC 
                         LIMIT 1),
                        0
                    ) as balance
            ),
            transaction_check AS (
                SELECT * FROM {schema_prefix}"CreditTransaction" 
                WHERE "transactionKey" = $1 AND "userId" = $2 AND "isActive" = false
            ),
            balance_update AS (
                INSERT INTO {schema_prefix}"UserBalance" ("userId", "balance", "updatedAt")
                SELECT 
                    $2::text,
                    user_balance_lock.balance + transaction_check.amount,
                    CURRENT_TIMESTAMP
                FROM user_balance_lock, transaction_check
                ON CONFLICT ("userId") DO UPDATE SET
                    "balance" = EXCLUDED."balance",
                    "updatedAt" = EXCLUDED."updatedAt"
                RETURNING "balance", "updatedAt"
            ),
            transaction_update AS (
                UPDATE {schema_prefix}"CreditTransaction"
                SET "transactionKey" = COALESCE($4, $1),
                    "isActive" = true,
                    "runningBalance" = balance_update.balance,
                    "createdAt" = balance_update."updatedAt",
                    "metadata" = $3::jsonb
                FROM balance_update, transaction_check
                WHERE {schema_prefix}"CreditTransaction"."transactionKey" = transaction_check."transactionKey"
                  AND {schema_prefix}"CreditTransaction"."userId" = transaction_check."userId"
                RETURNING {schema_prefix}"CreditTransaction"."runningBalance"
            )
            SELECT "runningBalance" as balance FROM transaction_update;
            """,
            transaction_key,  # $1
            user_id,  # $2
            dumps(metadata.data),  # $3 - use pre-serialized JSON string for JSONB
            new_transaction_key,  # $4
        )

        if result:
            # UserBalance is already updated by the CTE
            return result[0]["balance"]

    async def _add_transaction(
        self,
        user_id: str,
        amount: int,
        transaction_type: CreditTransactionType,
        is_active: bool = True,
        transaction_key: str | None = None,
        ceiling_balance: int | None = None,
        fail_insufficient_credits: bool = True,
        metadata: SafeJson = SafeJson({}),
    ) -> tuple[int, str]:
        """
        Add a new transaction for the user.
        This is the only method that should be used to add a new transaction.

        ATOMIC OPERATION DESIGN DECISION:
        ================================
        This method uses PostgreSQL row-level locking (FOR UPDATE) for atomic credit operations.
        After extensive analysis of concurrency patterns and correctness requirements, we determined
        that the FOR UPDATE approach is necessary despite the latency overhead.

        WHY FOR UPDATE LOCKING IS REQUIRED:
        ----------------------------------
        1. **Data Consistency**: Credit operations must be ACID-compliant. The balance check,
           calculation, and update must be atomic to prevent race conditions where:
           - Multiple spend operations could exceed available balance
           - Lost update problems could occur with concurrent top-ups
           - Refunds could create negative balances incorrectly

        2. **Serializability**: FOR UPDATE ensures operations are serialized at the database level,
           guaranteeing that each transaction sees a consistent view of the balance before applying changes.

        3. **Correctness Over Performance**: Financial operations require absolute correctness.
           The ~10-50ms latency increase from row locking is acceptable for the guarantee that
           no user will ever have an incorrect balance due to race conditions.

        4. **PostgreSQL Optimization**: Modern PostgreSQL versions optimize row locks efficiently.
           The performance cost is minimal compared to the complexity and risk of lock-free approaches.

        ALTERNATIVES CONSIDERED AND REJECTED:
        ------------------------------------
        - **Optimistic Concurrency**: Using version numbers or timestamps would require complex
          retry logic and could still fail under high contention scenarios.
        - **Application-Level Locking**: Redis locks or similar would add network overhead and
          single points of failure while being less reliable than database locks.
        - **Event Sourcing**: Would require complete architectural changes and eventual consistency
          models that don't fit our real-time balance requirements.

        PERFORMANCE CHARACTERISTICS:
        ---------------------------
        - Single user operations: 10-50ms latency (acceptable for financial operations)
        - Concurrent operations on same user: Serialized (prevents data corruption)
        - Concurrent operations on different users: Fully parallel (no blocking)

        This design prioritizes correctness and data integrity over raw performance,
        which is the appropriate choice for a credit/payment system.

        Args:
            user_id (str): The user ID.
            amount (int): The amount of credits to add.
            transaction_type (CreditTransactionType): The type of transaction.
            is_active (bool): Whether the transaction is active or needs to be manually activated through _enable_transaction.
            transaction_key (str | None): The transaction key. Avoids adding transaction if the key already exists.
            ceiling_balance (int | None): The ceiling balance. Avoids adding more credits if the balance is already above the ceiling.
            fail_insufficient_credits (bool): Whether to fail if the user has insufficient credits.
            metadata (Json): The metadata of the transaction.

        Returns:
            tuple[int, str]: The new balance & the transaction key.
        """
        # Quick validation for ceiling balance to avoid unnecessary database operations
        if ceiling_balance and amount > 0:
            current_balance, _ = await self._get_credits(user_id)
            if current_balance >= ceiling_balance:
                raise ValueError(
                    f"You already have enough balance of ${current_balance/100}, top-up is not required when you already have at least ${ceiling_balance/100}"
                )

        # Single unified atomic operation for all transaction types using UserBalance
        try:
            result = await query_raw_with_schema(
                """
                WITH user_balance_lock AS (
                    SELECT 
                        $1::text as userId, 
                        -- CRITICAL: FOR UPDATE lock prevents concurrent modifications to the same user's balance
                        -- This ensures atomic read-modify-write operations and prevents race conditions
                        COALESCE(
                            (SELECT balance FROM {schema_prefix}"UserBalance" WHERE "userId" = $1 FOR UPDATE),
                            -- Fallback: compute balance from transaction history if UserBalance doesn't exist
                            (SELECT COALESCE(ct."runningBalance", 0) 
                             FROM {schema_prefix}"CreditTransaction" ct 
                             WHERE ct."userId" = $1 
                               AND ct."isActive" = true 
                               AND ct."runningBalance" IS NOT NULL 
                             ORDER BY ct."createdAt" DESC 
                             LIMIT 1),
                            0
                        ) as balance
                ),
                balance_update AS (
                    INSERT INTO {schema_prefix}"UserBalance" ("userId", "balance", "updatedAt")
                    SELECT 
                        $1::text,
                        CASE 
                            -- For inactive transactions: Don't update balance
                            WHEN $5::boolean = false THEN user_balance_lock.balance
                            -- For ceiling balance (amount > 0): Apply ceiling
                            WHEN $2 > 0 AND $7::int IS NOT NULL AND user_balance_lock.balance > $7::int - $2 THEN $7::int
                            -- For regular operations: Apply with overflow/underflow protection  
                            WHEN user_balance_lock.balance + $2 > $6::int THEN $6::int
                            WHEN user_balance_lock.balance + $2 < $10::int THEN $10::int
                            ELSE user_balance_lock.balance + $2
                        END,
                        CURRENT_TIMESTAMP
                    FROM user_balance_lock
                    WHERE (
                        $5::boolean = false OR  -- Allow inactive transactions
                        $2 >= 0 OR              -- Allow positive amounts (top-ups, grants)
                        $8::boolean = false OR  -- Allow when insufficient balance check is disabled
                        user_balance_lock.balance + $2 >= 0  -- Allow spending only when sufficient balance
                    )
                    ON CONFLICT ("userId") DO UPDATE SET
                        "balance" = EXCLUDED."balance",
                        "updatedAt" = EXCLUDED."updatedAt"
                    RETURNING "balance", "updatedAt"
                ),
                transaction_insert AS (
                    INSERT INTO {schema_prefix}"CreditTransaction" (
                        "userId", "amount", "type", "runningBalance", 
                        "metadata", "isActive", "createdAt", "transactionKey"
                    )
                    SELECT 
                        $1::text,
                        $2::int,
                        $3::text::{schema_prefix}"CreditTransactionType",
                        CASE 
                            -- For inactive transactions: Set runningBalance to original balance (don't apply the change yet)
                            WHEN $5::boolean = false THEN user_balance_lock.balance
                            ELSE COALESCE(balance_update.balance, user_balance_lock.balance)
                        END,
                        $4::jsonb,
                        $5::boolean,
                        COALESCE(balance_update."updatedAt", CURRENT_TIMESTAMP),
                        COALESCE($9, gen_random_uuid()::text)
                    FROM user_balance_lock
                    LEFT JOIN balance_update ON true
                    WHERE (
                        $5::boolean = false OR  -- Allow inactive transactions
                        $2 >= 0 OR              -- Allow positive amounts (top-ups, grants)
                        $8::boolean = false OR  -- Allow when insufficient balance check is disabled
                        user_balance_lock.balance + $2 >= 0  -- Allow spending only when sufficient balance
                    )
                    RETURNING "runningBalance", "transactionKey"
                )
                SELECT "runningBalance" as balance, "transactionKey" FROM transaction_insert;
                """,
                user_id,  # $1
                amount,  # $2
                transaction_type.value,  # $3
                dumps(metadata.data),  # $4 - use pre-serialized JSON string for JSONB
                is_active,  # $5
                POSTGRES_INT_MAX,  # $6 - overflow protection
                ceiling_balance,  # $7 - ceiling balance (nullable)
                fail_insufficient_credits,  # $8 - check balance for spending
                transaction_key,  # $9 - transaction key (nullable)
                POSTGRES_INT_MIN,  # $10 - underflow protection
            )
        except Exception as e:
            # Convert raw SQL unique constraint violations to UniqueViolationError
            # for consistent exception handling throughout the codebase
            error_str = str(e).lower()
            if (
                "already exists" in error_str
                or "duplicate key" in error_str
                or "unique constraint" in error_str
            ):
                # Extract table and constraint info for better error messages
                # Re-raise as a UniqueViolationError but with proper format
                # Create a minimal data structure that the error constructor expects
                raise UniqueViolationError({"error": str(e), "user_facing_error": {}})
            # For any other error, re-raise as-is
            raise

        if result:
            new_balance, tx_key = result[0]["balance"], result[0]["transactionKey"]
            # UserBalance is already updated by the CTE
            return new_balance, tx_key

        # If no result, either user doesn't exist or insufficient balance
        user = await User.prisma().find_unique(where={"id": user_id})
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Must be insufficient balance for spending operation
        if amount < 0 and fail_insufficient_credits:
            current_balance, _ = await self._get_credits(user_id)
            raise InsufficientBalanceError(
                message=f"Insufficient balance of ${current_balance/100}, where this will cost ${abs(amount)/100}",
                user_id=user_id,
                balance=current_balance,
                amount=amount,
            )

        # Unexpected case
        raise ValueError(f"Transaction failed for user {user_id}, amount {amount}")


