"""Event definitions for event sourcing architecture."""
import json
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel
from uuid import UUID, uuid4


class EventType(str, Enum):
    # Player events
    PLAYER_CONNECTED = "player.connected"
    PLAYER_DISCONNECTED = "player.disconnected"
    PLAYER_AUTHENTICATED = "player.authenticated"
    
    # Matchmaking events
    MATCHMAKING_JOINED = "matchmaking.joined"
    MATCHMAKING_CANCELLED = "matchmaking.cancelled"
    MATCH_FOUND = "match.found"
    
    # Lobby events
    LOBBY_CREATED = "lobby.created"
    LOBBY_JOINED = "lobby.joined"
    LOBBY_LEFT = "lobby.left"
    LOBBY_READY = "lobby.ready"
    
    # Game session events
    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"
    GAME_STATE_UPDATE = "game.state_update"
    PLAYER_ACTION = "player.action"
    
    # Leaderboard events
    SCORE_UPDATED = "score.updated"
    RANKING_CHANGED = "ranking.changed"
    
    # Chat events
    MESSAGE_SENT = "message.sent"
    CHANNEL_JOINED = "channel.joined"
    CHANNEL_LEFT = "channel.left"
    
    # Notification events
    NOTIFICATION_SENT = "notification.sent"
    NOTIFICATION_READ = "notification.read"


class Event(BaseModel):
    id: UUID = uuid4()
    type: EventType
    timestamp: datetime = datetime.utcnow()
    payload: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "payload": json.dumps(self.payload),
            "metadata": json.dumps(self.metadata or {})
        }


# Event store interface
class EventStore:
    """Abstract event store for event sourcing."""
    
    async def append(self, stream_id: str, event: Event) -> None:
        raise NotImplementedError
    
    async def read_stream(self, stream_id: str, from_version: int = 0) -> list[Event]:
        raise NotImplementedError
    
    async def get_all_events(self, event_types: list[EventType] = None, 
                             from_position: int = 0, limit: int = 100) -> list[Event]:
        raise NotImplementedError


# Redis event store implementation
class RedisEventStore(EventStore):
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def append(self, stream_id: str, event: Event) -> None:
        key = f"events:{stream_id}"
        # Redis XADD requires all values to be strings
        event_data = event.to_dict()
        await self.redis.xadd(key, event_data)
        # Also publish for real-time consumers
        serializable = {
            "id": event_data["id"],
            "type": event_data["type"],
            "timestamp": event_data["timestamp"],
            "payload": event.payload,
            "metadata": event.metadata or {}
        }
        await self.redis.publish(f"stream:{stream_id}", json.dumps(serializable))
    
    async def read_stream(self, stream_id: str, from_version: int = 0) -> list[Event]:
        key = f"events:{stream_id}"
        entries = await self.redis.xrange(key)
        events = []
        for entry_id, fields in entries[from_version:]:
            events.append(Event(
                type=EventType(fields["type"]),
                payload=json.loads(fields["payload"]),
                metadata=json.loads(fields["metadata"]) if "metadata" in fields else None
            ))
        return events
    
    async def get_all_events(self, event_types: list[EventType] = None, 
                             from_position: int = 0, limit: int = 100) -> list[Event]:
        # Scan all event streams
        streams = []
        async for key in self.redis.scan_iter(match="events:*"):
            streams.append(key)
        
        all_events = []
        for stream in streams:
            events = await self.read_stream(stream.decode().replace("events:", ""), from_version=from_position)
            all_events.extend(events)
        
        if event_types:
            all_events = [e for e in all_events if e.type in event_types]
        
        return sorted(all_events, key=lambda e: e.timestamp)[from_position:from_position + limit]
