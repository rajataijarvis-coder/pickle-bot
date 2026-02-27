# src/picklebot/events/delivery.py
import logging
from typing import TYPE_CHECKING, Any

from .bus import EventBus
from .types import Event, EventType

if TYPE_CHECKING:
    from picklebot.core.context import SharedContext

logger = logging.getLogger(__name__)

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


class DeliveryWorker:
    """Worker that delivers outbound messages to platforms."""

    def __init__(self, context: "SharedContext"):
        self.context = context
        self.logger = logging.getLogger("picklebot.events.DeliveryWorker")

    async def handle_event(self, event: Event) -> None:
        """Handle an outbound message event."""
        if event.type != EventType.OUTBOUND:
            return

        try:
            # Look up where to deliver
            platform_info = self._lookup_platform(event.session_id)
            platform = platform_info["platform"]

            # Get limit and chunk
            limit = PLATFORM_LIMITS.get(platform, float("inf"))
            if limit != float("inf"):
                limit = int(limit)
            chunks = chunk_message(
                event.content,
                int(limit) if limit != float("inf") else len(event.content),
            )

            # Deliver each chunk
            for chunk in chunks:
                await self._deliver(platform, platform_info, chunk)

            # Ack the event
            filename = f"{event.timestamp}_{event.session_id}.json"
            self.context.eventbus.ack(filename)

            self.logger.info(
                f"Delivered message to {platform} for session {event.session_id}"
            )

        except Exception as e:
            self.logger.error(f"Failed to deliver message: {e}")
            # TODO: Retry logic with backoff

    def _lookup_platform(self, session_id: str) -> dict[str, Any]:
        """Look up platform and delivery context for a session."""
        # Check runtime config for session -> platform mapping
        runtime_config = self.context.config.runtime

        # Look in messagebus config for session
        if "messagebus" in runtime_config:
            for platform in ["telegram", "discord"]:
                platform_config = runtime_config.get("messagebus", {}).get(platform, {})
                sessions = platform_config.get("sessions", {})
                for user_id, sess_id in sessions.items():
                    if sess_id == session_id:
                        delivery_context = {}
                        if platform == "telegram":
                            delivery_context["chat_id"] = platform_config.get(
                                "default_chat_id", ""
                            )
                        elif platform == "discord":
                            delivery_context["channel_id"] = platform_config.get(
                                "default_chat_id", ""
                            )
                        return {
                            "platform": platform,
                            **delivery_context,
                        }

        # Default to CLI if not found
        return {"platform": "cli"}

    async def _deliver(
        self, platform: str, platform_info: dict[str, Any], content: str
    ) -> None:
        """Deliver a message chunk to a platform."""
        if platform == "telegram":
            chat_id = platform_info.get("chat_id")
            if chat_id and hasattr(self.context, "telegram_bus"):
                await self.context.telegram_bus.send(chat_id, content)
        elif platform == "discord":
            channel_id = platform_info.get("channel_id")
            if channel_id and hasattr(self.context, "discord_bus"):
                await self.context.discord_bus.send(channel_id, content)
        elif platform == "cli":
            # CLI just prints to stdout
            print(content)

    def subscribe(self, eventbus: EventBus) -> None:
        """Subscribe this worker to an event bus."""
        eventbus.subscribe(EventType.OUTBOUND, self.handle_event)
