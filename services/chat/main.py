"""
Chat Service - Manages chat channels and messaging.
"""
import asyncio
import json
import os
from typing import Dict, Set, Optional
from uuid import UUID
from datetime import datetime

from fastapi import FastAPI

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.redis_client import redis_client
from shared.types import ChatMessage
from shared.events import Event, EventType, RedisEventStore


app = FastAPI(title="Chat Service", version="1.0.0")


class ChatManager:
    """Manages chat channels and messages."""
    
    def __init__(self):
        # Track which players are in which channels
        self.channel_members: Dict[str, Set[str]] = {}
    
    async def join_channel(self, channel_id: str, player_id: UUID) -> bool:
        """Add player to channel."""
        if channel_id not in self.channel_members:
            self.channel_members[channel_id] = set()
        
        self.channel_members[channel_id].add(str(player_id))
        
        # Store in Redis for distributed state
        await redis_client.redis.sadd(f"chat:channel:{channel_id}:members", str(player_id))
        
        # Publish join event
        await redis_client.publish("gateway:chat_message", {
            "target_player_id": str(player_id),
            "event_type": "chat.joined",
            "payload": {
                "channel_id": channel_id,
                "message": f"Joined channel {channel_id}"
            }
        })
        
        return True
    
    async def leave_channel(self, channel_id: str, player_id: UUID) -> bool:
        """Remove player from channel."""
        player_id_str = str(player_id)
        
        if channel_id in self.channel_members:
            self.channel_members[channel_id].discard(player_id_str)
        
        # Remove from Redis
        await redis_client.redis.srem(f"chat:channel:{channel_id}:members", player_id_str)
        
        return True
    
    async def send_message(self, channel_id: str, sender_id: UUID,
                          content: str, sender_username: str = None,
                          metadata: dict = None) -> ChatMessage:
        """Send message to channel."""
        message = ChatMessage(
            channel_id=channel_id,
            sender_id=sender_id,
            sender_username=sender_username,
            content=content,
            metadata=metadata
        )
        
        # Store message in Redis (keep last 100 messages per channel)
        message_data = message.model_dump(mode="json")
        await redis_client.redis.lpush(f"chat:channel:{channel_id}:messages", json.dumps(message_data))
        await redis_client.redis.ltrim(f"chat:channel:{channel_id}:messages", 0, 99)
        
        return message
    
    async def get_channel_messages(self, channel_id: str, limit: int = 50) -> list[ChatMessage]:
        """Get recent messages from channel."""
        messages_raw = await redis_client.redis.lrange(
            f"chat:channel:{channel_id}:messages", 0, limit - 1
        )
        
        messages = []
        for raw in reversed(messages_raw):  # Reverse to get chronological order
            try:
                data = json.loads(raw)
                messages.append(ChatMessage(**data))
            except:
                pass
        
        return messages
    
    async def get_channel_members(self, channel_id: str) -> list[str]:
        """Get channel members."""
        # Try local first, then Redis
        if channel_id in self.channel_members:
            return list(self.channel_members[channel_id])
        
        # Get from Redis
        members = await redis_client.redis.smembers(f"chat:channel:{channel_id}:members")
        return [m.decode() if isinstance(m, bytes) else m for m in members]
    
    async def broadcast_to_channel(self, channel_id: str, message: dict, 
                                   exclude: Set[str] = None) -> int:
        """Broadcast message to all channel members."""
        members = await self.get_channel_members(channel_id)
        exclude = exclude or set()
        
        count = 0
        for member_id in members:
            if member_id not in exclude:
                await redis_client.publish("gateway:chat_message", {
                    "target_player_id": member_id,
                    "event_type": message.get("type"),
                    "payload": message.get("data")
                })
                count += 1
        
        return count
    
    async def create_direct_channel(self, player1_id: UUID, player2_id: UUID) -> str:
        """Create private/direct chat channel between two players."""
        # Sort IDs for consistent channel naming
        ids = sorted([str(player1_id), str(player2_id)])
        channel_id = f"dm:{ids[0]}:{ids[1]}"
        
        # Add both players
        await self.join_channel(channel_id, player1_id)
        await self.join_channel(channel_id, player2_id)
        
        return channel_id
    
    async def is_player_in_channel(self, channel_id: str, player_id: UUID) -> bool:
        """Check if player is in channel."""
        members = await self.get_channel_members(channel_id)
        return str(player_id) in members


chat_manager = ChatManager()
event_store: RedisEventStore = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "chat",
        "active_channels": len(chat_manager.channel_members)
    }


@app.get("/channels/{channel_id}/messages")
async def get_messages(channel_id: str, limit: int = 50):
    """Get channel messages."""
    messages = await chat_manager.get_channel_messages(channel_id, limit)
    return {
        "channel_id": channel_id,
        "messages": [m.model_dump(mode="json") for m in messages]
    }


@app.get("/channels/{channel_id}/members")
async def get_members(channel_id: str):
    """Get channel members."""
    members = await chat_manager.get_channel_members(channel_id)
    return {
        "channel_id": channel_id,
        "members": members
    }


async def handle_chat_join(data: dict):
    """Handle chat channel join."""
    player_id = UUID(data["player_id"])
    channel_id = data["channel_id"]
    
    await chat_manager.join_channel(channel_id, player_id)
    
    # Load and send recent messages
    messages = await chat_manager.get_channel_messages(channel_id, 20)
    
    await redis_client.publish("gateway:chat_message", {
        "target_player_id": str(player_id),
        "event_type": "chat.history",
        "payload": {
            "channel_id": channel_id,
            "messages": [m.model_dump(mode="json") for m in messages]
        }
    })
    
    # Emit event
    event = Event(
        type=EventType.CHANNEL_JOINED,
        payload={
            "channel_id": channel_id,
            "player_id": str(player_id)
        }
    )
    await event_store.append(f"chat:{channel_id}", event)


async def handle_chat_message(data: dict):
    """Handle chat message."""
    sender_id = UUID(data["sender_id"])
    channel_id = data["channel_id"]
    content = data["content"]
    
    # Check if sender is in channel
    if not await chat_manager.is_player_in_channel(channel_id, sender_id):
        # Auto-join if not in channel (for global/lobby channels)
        await chat_manager.join_channel(channel_id, sender_id)
    
    # Look up sender username
    username_data = await redis_client.get_state(f"player:{sender_id}:username")
    sender_username = username_data.get("username") if username_data else str(sender_id)

    # Create and store message
    message = await chat_manager.send_message(
        channel_id, sender_id, content,
        sender_username=sender_username,
        metadata=data.get("metadata")
    )
    
    # Emit event
    event = Event(
        type=EventType.MESSAGE_SENT,
        payload={
            "channel_id": channel_id,
            "sender_id": str(sender_id),
            "content": content,
            "message_id": str(message.id)
        }
    )
    await event_store.append(f"chat:{channel_id}", event)
    
    # Broadcast to channel
    await chat_manager.broadcast_to_channel(channel_id, {
        "type": "chat.message",
        "data": {
            "channel_id": channel_id,
            "message": message.model_dump(mode="json")
        }
    })


async def handle_player_disconnected(data: dict):
    """Handle player disconnect - remove from channels."""
    player_id = data.get("player_id")
    
    # Remove from all channels
    for channel_id in list(chat_manager.channel_members.keys()):
        if player_id in chat_manager.channel_members[channel_id]:
            await chat_manager.leave_channel(channel_id, UUID(player_id))
            
            # Notify remaining members
            await chat_manager.broadcast_to_channel(channel_id, {
                "type": "chat.system",
                "data": {
                    "channel_id": channel_id,
                    "message": f"Player {player_id} left"
                }
            })


async def subscribe_to_events():
    """Subscribe to chat events."""
    pubsub = await redis_client.subscribe("chat:join", "chat:message", "player:disconnected")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                channel = message["channel"]
                
                if channel == "chat:join":
                    await handle_chat_join(data)
                elif channel == "chat:message":
                    await handle_chat_message(data)
                elif channel == "player:disconnected":
                    await handle_player_disconnected(data)
                    
            except Exception as e:
                print(f"Error processing chat event: {e}")


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    global event_store
    await redis_client.connect()
    event_store = RedisEventStore(redis_client.redis)
    
    # Start background tasks
    asyncio.create_task(subscribe_to_events())
    
    # Register service
    await redis_client.register_service(
        "chat",
        os.getenv("HOSTNAME", "chat-1"),
        "0.0.0.0",
        int(os.getenv("PORT", 3005))
    )
    
    print("Chat Service started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await redis_client.disconnect()
    print("Chat Service shutdown")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3005))
    uvicorn.run(app, host="0.0.0.0", port=port)
