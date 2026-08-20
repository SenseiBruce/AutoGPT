"""Notification queue configuration and enqueue helpers."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

import aio_pika
from prisma.enums import NotificationType

from backend.data import rabbitmq
from backend.data.notifications import (
    BaseEventModel,
    BaseSummaryData,
    BaseSummaryParams,
    DailySummaryData,
    DailySummaryParams,
    NotificationEventModel,
    NotificationResult,
    NotificationTypeOverride,
    QueueType,
    SummaryParamsEventModel,
    WeeklySummaryData,
    WeeklySummaryParams,
    get_batch_delay,
    get_notif_data_type,
    get_summary_params_type,
)
from backend.data.rabbitmq import Exchange, ExchangeType, Queue, RabbitMQConfig
from backend.data.user import (
    disable_all_user_notifications,
    generate_unsubscribe_link,
    set_user_email_verification,
)
from backend.notifications.email import EmailSender
from backend.util.clients import get_database_manager_async_client
from backend.util.logging import TruncatedLogger
from backend.util.metrics import DiscordChannel, discord_send_alert
from backend.util.retry import continuous_retry
from backend.util.service import (
    AppService,
    AppServiceClient,
    UnhealthyServiceError,
    endpoint_to_sync,
    expose,
)
from backend.util.settings import AppEnvironment, Settings

logger = TruncatedLogger(logging.getLogger(__name__), "[NotificationManager]")
settings = Settings()


NOTIFICATION_EXCHANGE = Exchange(name="notifications", type=ExchangeType.TOPIC)
DEAD_LETTER_EXCHANGE = Exchange(name="dead_letter", type=ExchangeType.TOPIC)
EXCHANGES = [NOTIFICATION_EXCHANGE, DEAD_LETTER_EXCHANGE]


def create_notification_config() -> RabbitMQConfig:
    """Create RabbitMQ configuration for notifications"""

    queues = [
        # Main notification queues
        Queue(
            name="immediate_notifications",
            exchange=NOTIFICATION_EXCHANGE,
            routing_key="notification.immediate.#",
            arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name,
                "x-dead-letter-routing-key": "failed.immediate",
            },
        ),
        Queue(
            name="admin_notifications",
            exchange=NOTIFICATION_EXCHANGE,
            routing_key="notification.admin.#",
            arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name,
                "x-dead-letter-routing-key": "failed.admin",
            },
        ),
        # Summary notification queues
        Queue(
            name="summary_notifications",
            exchange=NOTIFICATION_EXCHANGE,
            routing_key="notification.summary.#",
            arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name,
                "x-dead-letter-routing-key": "failed.summary",
            },
        ),
        # Batch Queue
        Queue(
            name="batch_notifications",
            exchange=NOTIFICATION_EXCHANGE,
            routing_key="notification.batch.#",
            arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name,
                "x-dead-letter-routing-key": "failed.batch",
            },
        ),
        # Failed notifications queue
        Queue(
            name="failed_notifications",
            exchange=DEAD_LETTER_EXCHANGE,
            routing_key="failed.#",
        ),
    ]

    return RabbitMQConfig(
        exchanges=EXCHANGES,
        queues=queues,
    )


def get_routing_key(event_type: NotificationType) -> str:
    strategy = NotificationTypeOverride(event_type).strategy
    """Get the appropriate routing key for an event"""
    if strategy == QueueType.IMMEDIATE:
        return f"notification.immediate.{event_type.value}"
    elif strategy == QueueType.BACKOFF:
        return f"notification.backoff.{event_type.value}"
    elif strategy == QueueType.ADMIN:
        return f"notification.admin.{event_type.value}"
    elif strategy == QueueType.BATCH:
        return f"notification.batch.{event_type.value}"
    elif strategy == QueueType.SUMMARY:
        return f"notification.summary.{event_type.value}"
    return f"notification.{event_type.value}"


def queue_notification(event: NotificationEventModel) -> NotificationResult:
    """Queue a notification - exposed method for other services to call"""
    # Disable in production
    if settings.config.app_env == AppEnvironment.PRODUCTION:
        return NotificationResult(
            success=True,
            message="Queueing notifications is disabled in production",
        )
    try:
        logger.debug(f"Received Request to queue {event=}")

        exchange = "notifications"
        routing_key = get_routing_key(event.type)

        from backend.util.clients import get_notification_queue

        queue = get_notification_queue()
        queue.publish_message(
            routing_key=routing_key,
            message=event.model_dump_json(),
            exchange=next(ex for ex in EXCHANGES if ex.name == exchange),
        )

        return NotificationResult(
            success=True,
            message=f"Notification queued with routing key: {routing_key}",
        )

    except Exception as e:
        logger.exception(f"Error queueing notification: {e}")
        return NotificationResult(success=False, message=str(e))


async def queue_notification_async(event: NotificationEventModel) -> NotificationResult:
    """Queue a notification - exposed method for other services to call"""
    # Disable in production
    if settings.config.app_env == AppEnvironment.PRODUCTION:
        return NotificationResult(
            success=True,
            message="Queueing notifications is disabled in production",
        )
    try:
        logger.debug(f"Received Request to queue {event=}")

        exchange = "notifications"
        routing_key = get_routing_key(event.type)

        from backend.util.clients import get_async_notification_queue

        queue = await get_async_notification_queue()
        await queue.publish_message(
            routing_key=routing_key,
            message=event.model_dump_json(),
            exchange=next(ex for ex in EXCHANGES if ex.name == exchange),
        )

        return NotificationResult(
            success=True,
            message=f"Notification queued with routing key: {routing_key}",
        )

    except Exception as e:
        logger.exception(f"Error queueing notification: {e}")
        return NotificationResult(success=False, message=str(e))


