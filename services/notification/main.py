"""
Notification Service - Manages notifications and alerts.
"""
import asyncio
import json
import os
from typing import Dict, List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timedelta

from fastapi import FastAPI

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.redis_client import redis_client
from shared.types import Notification
from shared.events import Event, EventType, RedisEventStore


app = FastAPI(title="Notification Service", version="1.0.0")


class NotificationManager:
    """Manages user notifications."""
    
    def __init__(self):
        # Track unread counts per player
        self.unread_counts: Dict[str, int] = {}
    
    async def create_notification(self, recipient_id: UUID, title: str, 
                                  message: str, notification_type: str,
                                  data: dict = None) -> Notification:
        """Create and store notification."""
        notification = Notification(
            id=uuid4(),
            recipient_id=recipient_id,
            title=title,
            message=message,
            type=notification_type,
            data=data or {}
        )
        
        # Store in Redis
        key = f"notifications:{recipient_id}"
        await redis_client.redis.lpush(key, notification.model_dump_json())
        
        # Keep only last 100 notifications
        await redis_client.redis.ltrim(key, 0, 99)
        
        # Increment unread count
        await redis_client.redis.hincrby(f"notifications:{recipient_id}:unread", "count", 1)
        
        return notification
    
    async def get_notifications(self, recipient_id: UUID, 
                                 unread_only: bool = False,
                                 limit: int = 50) -> List[Notification]:
        """Get notifications for player."""
        key = f"notifications:{recipient_id}"
        
        # Get all notifications
        notifications_raw = await redis_client.redis.lrange(key, 0, limit - 1)
        
        notifications = []
        for raw in notifications_raw:
            try:
                data = json.loads(raw)
                notification = Notification(**data)
                
                if not unread_only or not notification.read:
                    notifications.append(notification)
            except:
                pass
        
        return notifications
    
    async def mark_read(self, recipient_id: UUID, 
                       notification_id: Optional[UUID] = None) -> int:
        """Mark notification(s) as read."""
        key = f"notifications:{recipient_id}"
        
        # Get all notifications
        notifications_raw = await redis_client.redis.lrange(key, 0, -1)
        
        marked_count = 0
        updated_notifications = []
        
        for raw in notifications_raw:
            try:
                data = json.loads(raw)
                notification = Notification(**data)
                
                if notification_id is None or notification.id == notification_id:
                    if not notification.read:
                        notification.read = True
                        marked_count += 1
                
                updated_notifications.append(notification.model_dump_json())
            except:
                pass
        
        # Store updated notifications
        if updated_notifications:
            await redis_client.redis.delete(key)
            await redis_client.redis.lpush(key, *updated_notifications)
        
        # Update unread count
        if marked_count > 0:
            await redis_client.redis.hincrby(
                f"notifications:{recipient_id}:unread", 
                "count", 
                -marked_count
            )
        
        return marked_count
    
    async def get_unread_count(self, recipient_id: UUID) -> int:
        """Get unread notification count."""
        count = await redis_client.redis.hget(
            f"notifications:{recipient_id}:unread", 
            "count"
        )
        return int(count) if count else 0
    
    async def delete_notification(self, recipient_id: UUID, 
                                   notification_id: UUID) -> bool:
        """Delete notification."""
        key = f"notifications:{recipient_id}"
        
        # Get all notifications
        notifications_raw = await redis_client.redis.lrange(key, 0, -1)
        
        updated_notifications = []
        deleted = False
        
        for raw in notifications_raw:
            try:
                data = json.loads(raw)
                if str(data.get("id")) != str(notification_id):
                    updated_notifications.append(raw)
                else:
                    deleted = True
                    # Decrement unread if notification was unread
                    if not data.get("read", True):
                        await redis_client.redis.hincrby(
                            f"notifications:{recipient_id}:unread",
                            "count",
                            -1
                        )
            except:
                pass
        
        if deleted:
            await redis_client.redis.delete(key)
            if updated_notifications:
                await redis_client.redis.lpush(key, *updated_notifications)
        
        return deleted


notification_manager = NotificationManager()
event_store: RedisEventStore = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "notification"}


@app.get("/notifications/{player_id}")
async def get_player_notifications(player_id: str, unread_only: bool = False):
    """Get player notifications."""
    notifications = await notification_manager.get_notifications(
        UUID(player_id), unread_only
    )
    return {
        "notifications": [n.model_dump(mode="json") for n in notifications]
    }


@app.get("/notifications/{player_id}/unread-count")
async def get_unread_count(player_id: str):
    """Get unread count."""
    count = await notification_manager.get_unread_count(UUID(player_id))
    return {"unread_count": count}


@app.post("/notifications/{player_id}/mark-read")
async def mark_notifications_read(player_id: str, notification_id: str = None):
    """Mark notifications as read."""
    nid = UUID(notification_id) if notification_id else None
    count = await notification_manager.mark_read(UUID(player_id), nid)
    return {"marked_read": count}


async def handle_send_notification(data: dict):
    """Handle send notification request."""
    recipient_id = UUID(data["recipient_id"])
    
    notification = await notification_manager.create_notification(
        recipient_id=recipient_id,
        title=data.get("title", "Notification"),
        message=data.get("message", ""),
        notification_type=data.get("type", "info"),
        data=data.get("data")
    )
    
    # Emit event
    event = Event(
        type=EventType.NOTIFICATION_SENT,
        payload={
            "notification_id": str(notification.id),
            "recipient_id": str(recipient_id),
            "type": notification.type
        }
    )
    await event_store.append(f"notifications:{recipient_id}", event)
    
    # Send to player via gateway
    await redis_client.publish("gateway:notification", {
        "target_player_id": str(recipient_id),
        "event_type": "notification.new",
        "payload": {
            "notification": notification.model_dump(mode="json"),
            "unread_count": await notification_manager.get_unread_count(recipient_id)
        }
    })


async def handle_match_found(data: dict):
    """Notify players of match found."""
    for player_id in data.get("players", []):
        await notification_manager.create_notification(
            recipient_id=UUID(player_id),
            title="Match Found!",
            message="A match has been found. Join now!",
            notification_type="match",
            data={"match_id": data.get("match_id")}
        )


async def handle_ranking_changed(data: dict):
    """Notify player of ranking change."""
    await notification_manager.create_notification(
        recipient_id=UUID(data["player_id"]),
        title="Ranking Changed!",
        message=f"Your rank changed from {data.get('old_rank')} to {data.get('new_rank')}",
        notification_type="ranking",
        data={
            "old_rank": data.get("old_rank"),
            "new_rank": data.get("new_rank"),
            "category": data.get("category", "global")
        }
    )


async def handle_lobby_ready(data: dict):
    """Notify players lobby is ready."""
    for player_id in data.get("players", []):
        await notification_manager.create_notification(
            recipient_id=UUID(player_id),
            title="Lobby Ready",
            message="All players are ready. Starting game soon...",
            notification_type="lobby",
            data={"lobby_id": data.get("lobby_id")}
        )


async def handle_broadcast(data: dict):
    """Broadcast notification to multiple players."""
    target_players = data.get("target_players", [])
    
    for player_id in target_players:
        await notification_manager.create_notification(
            recipient_id=UUID(player_id),
            title=data.get("title", "Broadcast"),
            message=data.get("message", ""),
            notification_type=data.get("type", "broadcast"),
            data=data.get("data")
        )


async def subscribe_to_events():
    """Subscribe to notification events."""
    channels = [
        "notification:send",
        "matchmaking:match_found",
        "leaderboard:ranking_changed",
        "lobby:all_ready",
        "notification:broadcast"
    ]
    
    pubsub = await redis_client.subscribe(*channels)
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                channel = message["channel"]
                
                if channel == "notification:send":
                    await handle_send_notification(data)
                elif channel == "matchmaking:match_found":
                    await handle_match_found(data)
                elif channel == "leaderboard:ranking_changed":
                    await handle_ranking_changed(data)
                elif channel == "lobby:all_ready":
                    await handle_lobby_ready(data)
                elif channel == "notification:broadcast":
                    await handle_broadcast(data)
                    
            except Exception as e:
                print(f"Error processing notification event: {e}")


# Scheduled cleanup task
async def cleanup_old_notifications():
    """Clean up old notifications periodically."""
    while True:
        try:
            await asyncio.sleep(86400)  # Run daily
            # Cleanup logic here if needed
        except Exception as e:
            print(f"Cleanup error: {e}")


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    global event_store
    await redis_client.connect()
    event_store = RedisEventStore(redis_client.redis)
    
    # Start background tasks
    asyncio.create_task(subscribe_to_events())
    asyncio.create_task(cleanup_old_notifications())
    
    # Register service
    await redis_client.register_service(
        "notification",
        os.getenv("HOSTNAME", "notification-1"),
        "0.0.0.0",
        int(os.getenv("PORT", 3006))
    )
    
    print("Notification Service started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await redis_client.disconnect()
    print("Notification Service shutdown")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3006))
    uvicorn.run(app, host="0.0.0.0", port=port)
