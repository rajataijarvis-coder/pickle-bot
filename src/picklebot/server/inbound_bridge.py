"""Bridge for converting INBOUND events to agent Jobs."""

import asyncio
import logging
from typing import TYPE_CHECKING

from picklebot.core.agent import SessionMode
from picklebot.events.bus import EventBus
from picklebot.events.types import Event, EventType
from picklebot.server.base import Job

if TYPE_CHECKING:
    from picklebot.core.context import SharedContext

logger = logging.getLogger(__name__)


class InboundEventBridge:
    """Bridges INBOUND events to agent jobs.

    Subscribes to INBOUND events from the EventBus and creates Jobs
    for the AgentDispatcherWorker to process.
    """

    def __init__(self, context: "SharedContext", agent_id: str):
        self.context = context
        self.agent_id = agent_id
        self.logger = logging.getLogger("picklebot.server.InboundEventBridge")

    async def handle_inbound(self, event: Event) -> None:
        """Handle INBOUND event by creating a Job."""
        if event.type != EventType.INBOUND:
            return

        # Create a job for this inbound event
        job = Job(
            session_id=event.session_id,
            agent_id=self.agent_id,
            message=event.content,
            mode=SessionMode.CHAT,
        )
        # Create a new future for this job
        job.result_future = asyncio.get_event_loop().create_future()

        # Put job in queue for AgentDispatcherWorker
        await self.context.agent_queue.put(job)
        self.logger.debug(f"Created job for INBOUND event, session={event.session_id}")

    def subscribe(self, eventbus: EventBus) -> None:
        """Subscribe to INBOUND events."""
        eventbus.subscribe(EventType.INBOUND, self.handle_inbound)
        self.logger.info("InboundEventBridge subscribed to INBOUND events")
