"""Worker that delivers outbound messages to platforms."""

import logging
import random
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from picklebot.core.events import OutboundEvent
from picklebot.core.history import HistorySession
from .worker import SubscriberWorker

if TYPE_CHECKING:
    from picklebot.core.context import SharedContext
    from picklebot.messagebus.base import MessageBus

logger = logging.getLogger(__name__)

# Retry configuration
BACKOFF_MS = [5000, 25000, 120000, 600000]  # 5s, 25s, 2min, 10min
MAX_RETRIES = 5


def compute_backoff_ms(retry_count: int) -> int:
    """Compute backoff time with jitter.

    Args:
        retry_count: Current retry attempt (1-indexed)

    Returns:
        Backoff time in milliseconds
    """
    if retry_count <= 0:
        return 0

    # Cap at last backoff value
    idx = min(retry_count - 1, len(BACKOFF_MS) - 1)
    base = BACKOFF_MS[idx]

    # Add +/- 20% jitter
    jitter = random.randint(-base // 5, base // 5)
    return max(0, base + jitter)


# Platform message size limits
PLATFORM_LIMITS: dict[str, float] = {
    "telegram": 4096,
    "discord": 2000,
    "cli": float("inf"),  # no limit
}


def chunk_message(content: str, limit: int) -> list[str]:
    """Split message at paragraph boundaries, respecting limit.

    Args:
        content: The message to chunk
        limit: Maximum characters per chunk

    Returns:
        List of message chunks
    """
    if len(content) <= limit:
        return [content]

    chunks = []
    paragraphs = content.split("\n\n")
    current = ""

    for para in paragraphs:
        # Try to add to current chunk
        if current:
            potential = current + "\n\n" + para
        else:
            potential = para

        if len(potential) <= limit:
            current = potential
        else:
            # Current chunk is complete
            if current:
                chunks.append(current)

            # Handle paragraph that exceeds limit
            if len(para) > limit:
                # Hard split
                for i in range(0, len(para), limit):
                    chunks.append(para[i : i + limit])
                current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


class DeliveryWorker(SubscriberWorker):
    """Worker that delivers outbound messages to platforms."""

    def __init__(self, context: "SharedContext"):
        super().__init__(context)
        self.context.eventbus.subscribe(OutboundEvent, self.handle_event)
        self.logger.info("DeliveryWorker subscribed to OUTBOUND events")

    @lru_cache(maxsize=10)
    def _get_session_source(self, session_id: str) -> HistorySession | None:
        """Get session info from HistoryStore (cached)."""
        for session in self.context.history_store.list_sessions():
            if session.id == session_id:
                return session
        return None

    async def handle_event(self, event: OutboundEvent) -> None:
        """Handle an outbound message event."""
        try:
            session_info = self._get_session_source(event.session_id)

            if not session_info or not session_info.source:
                self.logger.warning(
                    f"No source for session {event.session_id}, skipping delivery"
                )
                return

            platform, user_id = session_info.source.split(":", 1)
            context = self._build_context(platform, user_id, session_info)

            limit = PLATFORM_LIMITS.get(platform, float("inf"))
            if limit != float("inf"):
                limit = int(limit)
            chunks = chunk_message(
                event.content,
                int(limit) if limit != float("inf") else len(event.content),
            )

            bus = self._get_bus(platform)
            if bus:
                for chunk in chunks:
                    await bus.reply(chunk, context)

            self.context.eventbus.ack(event)
            self.logger.info(
                f"Delivered message to {platform} for session {event.session_id}"
            )

        except Exception as e:
            self.logger.error(f"Failed to deliver message: {e}")

    def _build_context(
        self, platform: str, user_id: str, session_info: HistorySession
    ) -> Any:
        """Rebuild platform context from stored session info."""
        if platform == "telegram":
            from picklebot.messagebus.telegram_bus import TelegramContext

            return TelegramContext(user_id=user_id, chat_id=user_id)
        elif platform == "discord":
            from picklebot.messagebus.discord_bus import DiscordContext

            stored = session_info.context or {}
            return DiscordContext(
                user_id=user_id, channel_id=stored.get("channel_id", user_id)
            )
        elif platform == "cli":
            from picklebot.messagebus.cli_bus import CliContext

            return CliContext(user_id=user_id)
        else:
            raise ValueError(f"Unknown platform: {platform}")

    def _get_bus(self, platform: str) -> "MessageBus[Any] | None":
        """Get the message bus for a platform."""
        for bus in self.context.messagebus_buses:
            if bus.platform_name == platform:
                return bus
        return None
