"""Notification service public API."""

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

from .notifications_batch import NotificationBatchMixin
from .notifications_queue import (
    DEAD_LETTER_EXCHANGE,
    EXCHANGES,
    NOTIFICATION_EXCHANGE,
    create_notification_config,
    get_routing_key,
    queue_notification,
    queue_notification_async,
)

logger = TruncatedLogger(logging.getLogger(__name__), "[NotificationManager]")
settings = Settings()

class NotificationManager(NotificationBatchMixin, AppService):
    """Service for handling notifications with batching support"""

    def __init__(self):
        super().__init__()
        self.rabbitmq_config = create_notification_config()
        self.running = True
        self.email_sender = EmailSender()

    @property
    def rabbit(self) -> rabbitmq.AsyncRabbitMQ:
        """Access the RabbitMQ service. Will raise if not configured."""
        if not hasattr(self, "rabbitmq_service") or not self.rabbitmq_service:
            raise UnhealthyServiceError("RabbitMQ not configured for this service")
        return self.rabbitmq_service

    @property
    def rabbit_config(self) -> rabbitmq.RabbitMQConfig:
        """Access the RabbitMQ config. Will raise if not configured."""
        if not self.rabbitmq_config:
            raise UnhealthyServiceError("RabbitMQ not configured for this service")
        return self.rabbitmq_config

    async def health_check(self) -> str:
        # Service is unhealthy if RabbitMQ is not ready
        if not hasattr(self, "rabbitmq_service") or not self.rabbitmq_service:
            raise UnhealthyServiceError("RabbitMQ not configured for this service")
        if not self.rabbitmq_service.is_ready:
            raise UnhealthyServiceError("RabbitMQ channel is not ready")
        return await super().health_check()

    @classmethod
    def get_port(cls) -> int:
        return settings.config.notification_service_port

    @expose
    async def queue_weekly_summary(self):
        # disable in prod
        if settings.config.app_env == AppEnvironment.PRODUCTION:
            return
        # Use the existing event loop instead of creating a new one with asyncio.run()
        asyncio.create_task(self._queue_weekly_summary())

    async def _queue_weekly_summary(self):
        """Process weekly summary for specified notification types"""
        try:
            logger.info("Processing weekly summary queuing operation")
            processed_count = 0
            current_time = datetime.now(tz=timezone.utc)
            start_time = current_time - timedelta(days=7)
            logger.info(
                f"Querying for active users between {start_time} and {current_time}"
            )
            users = await get_database_manager_async_client(
                should_retry=False
            ).get_active_user_ids_in_timerange(
                end_time=current_time.isoformat(),
                start_time=start_time.isoformat(),
            )
            logger.info(f"Found {len(users)} active users in the last 7 days")
            for user in users:
                await self._queue_scheduled_notification(
                    SummaryParamsEventModel(
                        user_id=user,
                        type=NotificationType.WEEKLY_SUMMARY,
                        data=WeeklySummaryParams(
                            start_date=start_time,
                            end_date=current_time,
                        ),
                    ),
                )
                processed_count += 1

            logger.info(f"Processed {processed_count} weekly summaries into queue")

        except Exception as e:
            logger.exception(f"Error processing weekly summary: {e}")

    @expose
    async def _process_summary(self, message: str) -> bool:
        """Process a single notification with a summary strategy, returning whether to put into the failed queue"""
        try:
            logger.info(f"Processing summary notification: {message}")
            event = BaseEventModel.model_validate_json(message)
            model = SummaryParamsEventModel[
                get_summary_params_type(event.type)
            ].model_validate_json(message)

            logger.info(f"Processing summary notification: {model}")

            recipient_email = await get_database_manager_async_client(
                should_retry=False
            ).get_user_email_by_id(event.user_id)
            if not recipient_email:
                logger.error(f"User email not found for user {event.user_id}")
                return False
            should_send = await self._should_email_user_based_on_preference(
                event.user_id, event.type
            )
            if not should_send:
                logger.info(
                    f"User {event.user_id} does not want to receive {event.type} notifications"
                )
                return True

            summary_data = await self._gather_summary_data(
                event.user_id, event.type, model.data
            )

            unsub_link = generate_unsubscribe_link(event.user_id)

            data = NotificationEventModel(
                user_id=event.user_id,
                type=event.type,
                data=summary_data,
            )

            self.email_sender.send_templated(
                notification=event.type,
                user_email=recipient_email,
                data=data,
                user_unsub_link=unsub_link,
            )
            return True
        except Exception as e:
            logger.exception(f"Error processing notification for summary queue: {e}")
            return False

    async def _consume_queue(
        self,
        queue: aio_pika.abc.AbstractQueue,
        process_func: Callable[[str], Awaitable[bool]],
        queue_name: str,
    ):
        """Continuously consume messages from a queue using async iteration"""
        logger.info(f"Starting consumer for queue: {queue_name}")

        try:
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    if not self.running:
                        break

                    try:
                        async with message.process():
                            result = await process_func(message.body.decode())
                            if not result:
                                # Message will be rejected when exiting context without exception
                                raise aio_pika.exceptions.MessageProcessError(
                                    "Processing failed"
                                )
                    except aio_pika.exceptions.MessageProcessError:
                        # Let message.process() handle the rejection
                        pass
                    except Exception as e:
                        logger.error(f"Error processing message in {queue_name}: {e}")
                        # Let message.process() handle the rejection
                        raise
        except asyncio.CancelledError:
            logger.info(f"Consumer for {queue_name} cancelled")
            raise
        except Exception as e:
            logger.exception(f"Fatal error in consumer for {queue_name}: {e}")
            raise

    def run_service(self):
        # Queue the main _run_service task
        asyncio.run_coroutine_threadsafe(self._run_service(), self.shared_event_loop)

        # Start the main event loop
        super().run_service()

    @continuous_retry()
    async def _run_service(self):
        logger.info(f"[{self.service_name}] ⏳ Configuring RabbitMQ...")
        self.rabbitmq_service = rabbitmq.AsyncRabbitMQ(self.rabbitmq_config)
        await self.rabbitmq_service.connect()

        logger.info(f"[{self.service_name}] Started notification service")

        # Set up queue consumers with QoS settings
        channel = await self.rabbit.get_channel()

        # Set prefetch to prevent overwhelming the service
        await channel.set_qos(prefetch_count=10)

        immediate_queue = await channel.get_queue("immediate_notifications")
        batch_queue = await channel.get_queue("batch_notifications")
        admin_queue = await channel.get_queue("admin_notifications")
        summary_queue = await channel.get_queue("summary_notifications")

        # Create consumer tasks for each queue - running in parallel
        consumer_tasks = [
            asyncio.create_task(
                self._consume_queue(
                    queue=immediate_queue,
                    process_func=self._process_immediate,
                    queue_name="immediate_notifications",
                )
            ),
            asyncio.create_task(
                self._consume_queue(
                    queue=admin_queue,
                    process_func=self._process_admin_message,
                    queue_name="admin_notifications",
                )
            ),
            asyncio.create_task(
                self._consume_queue(
                    queue=batch_queue,
                    process_func=self._process_batch,
                    queue_name="batch_notifications",
                )
            ),
            asyncio.create_task(
                self._consume_queue(
                    queue=summary_queue,
                    process_func=self._process_summary,
                    queue_name="summary_notifications",
                )
            ),
        ]

        try:
            # Run all consumers concurrently
            await asyncio.gather(*consumer_tasks)
        except asyncio.CancelledError:
            logger.info("Service shutdown requested")
            # Cancel all consumer tasks
            for task in consumer_tasks:
                task.cancel()
            # Wait for all tasks to complete cancellation
            await asyncio.gather(*consumer_tasks, return_exceptions=True)
            raise

    def cleanup(self):
        """Cleanup service resources"""
        self.running = False
        logger.info("⏳ Disconnecting RabbitMQ...")
        self.run_and_wait(self.rabbitmq_service.disconnect())

        super().cleanup()


class NotificationManagerClient(AppServiceClient):
    @classmethod
    def get_service_type(cls):
        return NotificationManager

    process_existing_batches = endpoint_to_sync(
        NotificationManager.process_existing_batches
    )
    queue_weekly_summary = endpoint_to_sync(NotificationManager.queue_weekly_summary)
    discord_system_alert = endpoint_to_sync(NotificationManager.discord_system_alert)

