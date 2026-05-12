"""
Lobby Service - Manages game lobbies and player grouping.
"""
import asyncio
import json
import os
from typing import Dict, Set, Optional
from uuid import UUID, uuid4
from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.redis_client import redis_client
from shared.types import Lobby, GameMode, PlayerStatus
from shared.events import Event, EventType, RedisEventStore


app = FastAPI(title="Lobby Service", version="1.0.0")


class LobbyManager:
    """Manages active lobbies in distributed state."""
    
    def __init__(self):
        self.lobbies: Dict[str, Lobby] = {}  # local cache
        self.player_lobbies: Dict[str, str] = {}  # player_id -> lobby_id
    
    async def create_lobby(self, host_id: UUID, name: str, game_mode: GameMode, 
                           max_players: int = 8, settings: dict = None) -> Lobby:
        """Create a new lobby."""
        lobby_id = uuid4()
        
        lobby = Lobby(
            id=lobby_id,
            name=name,
            host_id=host_id,
            players=[host_id],
            max_players=max_players,
            game_mode=game_mode,
            settings=settings or {}
        )
        
        # Store in Redis (distributed state)
        await redis_client.set_state(
            f"lobby:{lobby_id}", 
            lobby.model_dump(mode="json"),
            expire=3600
        )
        
        self.lobbies[str(lobby_id)] = lobby
        self.player_lobbies[str(host_id)] = str(lobby_id)
        
        # Update player status
        await redis_client.set_state(
            f"player:{host_id}:status",
            {"status": PlayerStatus.IN_LOBBY.value, "lobby_id": str(lobby_id)}
        )
        
        return lobby
    
    async def join_lobby(self, lobby_id: str, player_id: UUID) -> Optional[Lobby]:
        """Add player to lobby."""
        # Get lobby from Redis
        lobby_data = await redis_client.get_state(f"lobby:{lobby_id}")
        if not lobby_data:
            raise HTTPException(status_code=404, detail="Lobby not found")
        
        lobby = Lobby(**lobby_data)
        
        # Check if lobby is full
        if len(lobby.players) >= lobby.max_players:
            raise HTTPException(status_code=400, detail="Lobby is full")
        
        # Check if already in lobby
        if player_id in lobby.players:
            return lobby
        
        # Add player
        lobby.players.append(player_id)
        
        # Save back to Redis
        await redis_client.set_state(
            f"lobby:{lobby_id}",
            lobby.model_dump(mode="json"),
            expire=3600
        )
        
        self.lobbies[lobby_id] = lobby
        self.player_lobbies[str(player_id)] = lobby_id
        
        # Update player status
        await redis_client.set_state(
            f"player:{player_id}:status",
            {"status": PlayerStatus.IN_LOBBY.value, "lobby_id": lobby_id}
        )
        
        return lobby
    
    async def leave_lobby(self, lobby_id: str, player_id: UUID) -> bool:
        """Remove player from lobby."""
        lobby_data = await redis_client.get_state(f"lobby:{lobby_id}")
        if not lobby_data:
            return False
        
        lobby = Lobby(**lobby_data)
        
        if player_id not in lobby.players:
            return False
        
        # Remove player
        lobby.players.remove(player_id)
        
        # If host leaves, assign new host or delete lobby
        if lobby.host_id == player_id:
            if lobby.players:
                lobby.host_id = lobby.players[0]
            else:
                # Delete empty lobby
                await redis_client.delete_state(f"lobby:{lobby_id}")
                if lobby_id in self.lobbies:
                    del self.lobbies[lobby_id]
                return True
        
        # Save back to Redis
        await redis_client.set_state(
            f"lobby:{lobby_id}",
            lobby.model_dump(mode="json"),
            expire=3600
        )
        
        self.lobbies[lobby_id] = lobby
        if str(player_id) in self.player_lobbies:
            del self.player_lobbies[str(player_id)]
        
        # Update player status
        await redis_client.set_state(
            f"player:{player_id}:status",
            {"status": PlayerStatus.ONLINE.value}
        )
        
        return True
    
    async def set_ready(self, lobby_id: str, player_id: UUID, ready: bool) -> bool:
        """Set player ready status."""
        # Store ready state
        await redis_client.set_state(
            f"lobby:{lobby_id}:ready:{player_id}",
            {"ready": ready, "timestamp": datetime.utcnow().isoformat()}
        )
        return True
    
    async def is_lobby_ready(self, lobby_id: str) -> bool:
        """Check if all players in lobby are ready."""
        lobby_data = await redis_client.get_state(f"lobby:{lobby_id}")
        if not lobby_data:
            return False
        
        lobby = Lobby(**lobby_data)
        
        # Check all players are ready
        for player_id in lobby.players:
            ready_data = await redis_client.get_state(f"lobby:{lobby_id}:ready:{player_id}")
            if not ready_data or not ready_data.get("ready"):
                return False
        
        return len(lobby.players) >= 2  # Minimum 2 players


lobby_manager = LobbyManager()
event_store: RedisEventStore = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "lobby",
        "active_lobbies": len(lobby_manager.lobbies)
    }


@app.get("/lobbies")
async def list_lobbies():
    """List all active lobbies."""
    result = []
    for lobby_id, lobby in lobby_manager.lobbies.items():
        result.append({
            "id": lobby_id,
            "name": lobby.name,
            "host_id": str(lobby.host_id),
            "players": [str(p) for p in lobby.players],
            "max_players": lobby.max_players,
            "game_mode": lobby.game_mode.value,
            "player_count": len(lobby.players)
        })
    return {"lobbies": result}


@app.get("/lobbies/{lobby_id}")
async def get_lobby(lobby_id: str):
    """Get lobby details."""
    lobby_data = await redis_client.get_state(f"lobby:{lobby_id}")
    if not lobby_data:
        raise HTTPException(status_code=404, detail="Lobby not found")
    
    return lobby_data


async def handle_lobby_create(data: dict):
    """Handle lobby creation request."""
    host_id = UUID(data["player_id"])
    
    lobby = await lobby_manager.create_lobby(
        host_id=host_id,
        name=data.get("name", "New Lobby"),
        game_mode=GameMode(data.get("game_mode", "casual")),
        max_players=data.get("max_players", 8),
        settings=data.get("settings", {})
    )
    
    # Emit event
    event = Event(
        type=EventType.LOBBY_CREATED,
        payload={
            "lobby_id": str(lobby.id),
            "host_id": str(host_id),
            "name": lobby.name
        }
    )
    await event_store.append(f"lobby:{lobby.id}", event)
    
    # Notify host
    await redis_client.publish("gateway:lobby_update", {
        "target_player_id": str(host_id),
        "event_type": "lobby.created",
        "payload": {
            "lobby_id": str(lobby.id),
            "lobby": lobby.model_dump(mode="json")
        }
    })


async def handle_lobby_join(data: dict):
    """Handle lobby join request."""
    player_id = UUID(data["player_id"])
    lobby_id = data["lobby_id"]
    
    try:
        lobby = await lobby_manager.join_lobby(lobby_id, player_id)
        
        # Emit event
        event = Event(
            type=EventType.LOBBY_JOINED,
            payload={
                "lobby_id": lobby_id,
                "player_id": str(player_id)
            }
        )
        await event_store.append(f"lobby:{lobby_id}", event)
        
        # Notify all players in lobby
        for pid in lobby.players:
            await redis_client.publish("gateway:lobby_update", {
                "target_player_id": str(pid),
                "event_type": "lobby.player_joined",
                "payload": {
                    "lobby_id": lobby_id,
                    "player_id": str(player_id),
                    "players": [str(p) for p in lobby.players]
                }
            })
        
    except HTTPException as e:
        # Notify player of error
        await redis_client.publish("gateway:error", {
            "target_player_id": str(player_id),
            "event_type": "lobby.join_failed",
            "payload": {"message": e.detail}
        })


async def handle_lobby_leave(data: dict):
    """Handle lobby leave request."""
    player_id = UUID(data["player_id"])
    lobby_id = data["lobby_id"]
    
    success = await lobby_manager.leave_lobby(lobby_id, player_id)
    
    if success:
        # Emit event
        event = Event(
            type=EventType.LOBBY_LEFT,
            payload={
                "lobby_id": lobby_id,
                "player_id": str(player_id)
            }
        )
        await event_store.append(f"lobby:{lobby_id}", event)
        
        # Get updated lobby data
        lobby_data = await redis_client.get_state(f"lobby:{lobby_id}")
        
        # Notify remaining players
        if lobby_data:
            lobby = Lobby(**lobby_data)
            for pid in lobby.players:
                await redis_client.publish("gateway:lobby_update", {
                    "target_player_id": str(pid),
                    "event_type": "lobby.player_left",
                    "payload": {
                        "lobby_id": lobby_id,
                        "player_id": str(player_id),
                        "players": [str(p) for p in lobby.players]
                    }
                })


async def handle_lobby_ready(data: dict):
    """Handle ready status change."""
    player_id = UUID(data["player_id"])
    lobby_id = data["lobby_id"]
    ready = data.get("ready", True)
    
    await lobby_manager.set_ready(lobby_id, player_id, ready)
    
    # Check if all ready
    all_ready = await lobby_manager.is_lobby_ready(lobby_id)
    
    if all_ready:
        # Emit lobby ready event
        event = Event(
            type=EventType.LOBBY_READY,
            payload={"lobby_id": lobby_id}
        )
        await event_store.append(f"lobby:{lobby_id}", event)
        
        # Notify all players
        lobby_data = await redis_client.get_state(f"lobby:{lobby_id}")
        if lobby_data:
            lobby = Lobby(**lobby_data)
            for pid in lobby.players:
                await redis_client.publish("gateway:lobby_update", {
                    "target_player_id": str(pid),
                    "event_type": "lobby.all_ready",
                    "payload": {
                        "lobby_id": lobby_id,
                        "message": "All players ready! Starting game..."
                    }
                })
        
        # Trigger game session creation
        await redis_client.publish("session:create_from_lobby", {
            "lobby_id": lobby_id,
            "players": [str(p) for p in lobby.players]
        })


async def subscribe_to_requests():
    """Subscribe to lobby requests."""
    pubsub = await redis_client.subscribe("lobby:create", "lobby:join", "lobby:leave", "lobby:ready")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                channel = message["channel"]
                
                if channel == "lobby:create":
                    await handle_lobby_create(data)
                elif channel == "lobby:join":
                    await handle_lobby_join(data)
                elif channel == "lobby:leave":
                    await handle_lobby_leave(data)
                elif channel == "lobby:ready":
                    await handle_lobby_ready(data)
                    
            except Exception as e:
                print(f"Error processing lobby request: {e}")


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    global event_store
    await redis_client.connect()
    event_store = RedisEventStore(redis_client.redis)
    
    # Start background tasks
    asyncio.create_task(subscribe_to_requests())
    
    # Register service
    await redis_client.register_service(
        "lobby",
        os.getenv("HOSTNAME", "lobby-1"),
        "0.0.0.0",
        int(os.getenv("PORT", 3002))
    )
    
    print("Lobby Service started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await redis_client.disconnect()
    print("Lobby Service shutdown")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3002))
    uvicorn.run(app, host="0.0.0.0", port=port)
