from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Types of events in the system."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"
    STATUS = "status"


@dataclass
class Event:
    """Platform-agnostic event."""

    type: EventType
    session_id: str
    content: str
    source: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dictionary."""
        return {
            "type": self.type.value,
            "session_id": self.session_id,
            "content": self.content,
            "source": self.source,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Deserialize event from dictionary."""
        return cls(
            type=EventType(data["type"]),
            session_id=data["session_id"],
            content=data["content"],
            source=data["source"],
            timestamp=data["timestamp"],
            metadata=data.get("metadata", {}),
        )
