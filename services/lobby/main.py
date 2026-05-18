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
        
        # Update player status
        await redis_client.set_state(
            f"player:{host_id}:status",
            {"status": PlayerStatus.IN_LOBBY.value, "lobby_id": str(lobby_id)},
            expire=300
        )
        await redis_client.redis.set(f"player:{host_id}:lobby_id", str(lobby_id))
        
        return lobby
    
    async def join_lobby(self, lobby_id: str, player_id: UUID) -> Optional[Lobby]:
        """Add player to lobby."""
        async with redis_client.lock(f"lobby_lock:{lobby_id}", timeout=5) as acquired:
            if not acquired:
                raise HTTPException(status_code=503, detail="Lobby is busy, try again")
                
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
            
            # Update player status
            await redis_client.set_state(
                f"player:{player_id}:status",
                {"status": PlayerStatus.IN_LOBBY.value, "lobby_id": lobby_id},
                expire=300
            )
            await redis_client.redis.set(f"player:{player_id}:lobby_id", str(lobby_id))
            
            return lobby
    
    async def leave_lobby(self, lobby_id: str, player_id: UUID) -> bool:
        """Remove player from lobby."""
        async with redis_client.lock(f"lobby_lock:{lobby_id}", timeout=5) as acquired:
            if not acquired:
                return False
                
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
                    await redis_client.redis.delete(f"player:{player_id}:lobby_id")
                    return True
            
            # Save back to Redis
            await redis_client.set_state(
                f"lobby:{lobby_id}",
                lobby.model_dump(mode="json"),
                expire=3600
            )
            
            # Update player status
            await redis_client.set_state(
                f"player:{player_id}:status",
                {"status": PlayerStatus.ONLINE.value},
                expire=300
            )
            await redis_client.redis.delete(f"player:{player_id}:lobby_id")
            
            return True
    
    async def set_ready(self, lobby_id: str, player_id: UUID, ready: bool) -> bool:
        """Set player ready status."""
        # Store ready state
        await redis_client.set_state(
            f"lobby:{lobby_id}:ready:{player_id}",
            {"ready": ready, "timestamp": datetime.utcnow().isoformat()},
            expire=3600
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

    async def get_enriched_players(self, player_ids: list[UUID]) -> list[dict]:
        """Get player IDs with usernames."""
        enriched = []
        for pid in player_ids:
            username = "Unknown"
            user_data = await redis_client.get_state(f"player:{pid}:username")
            if user_data:
                username = user_data.get("username", "Unknown")
            enriched.append({"id": str(pid), "username": username})
        return enriched


lobby_manager = LobbyManager()
event_store: RedisEventStore = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "lobby"
    }


@app.get("/lobbies")
async def list_lobbies():
    """List all active lobbies."""
    result = []
    # Note: Scanning all lobbies is not ideal for scaling, but good enough for now
    async for key in redis_client.redis.scan_iter(match="lobby:*"):
        key_str = key
        if ":ready:" not in key_str:
            lobby_data = await redis_client.get_state(key_str)
            if lobby_data and isinstance(lobby_data, dict):
                result.append({
                    "id": lobby_data["id"],
                    "name": lobby_data["name"],
                    "host_id": lobby_data["host_id"],
                    "players": lobby_data["players"],
                    "max_players": lobby_data["max_players"],
                    "game_mode": lobby_data["game_mode"],
                    "player_count": len(lobby_data["players"])
                })
    return {"lobbies": result}


@app.get("/lobbies/{lobby_id}")
async def get_lobby(lobby_id: str):
    """Get lobby details."""
    lobby_data = await redis_client.get_state(f"lobby:{lobby_id}")
    if not lobby_data:
        raise HTTPException(status_code=404, detail="Lobby not found")
    
    lobby = Lobby(**lobby_data)
    enriched_players = await lobby_manager.get_enriched_players(lobby.players)
    
    result = lobby.model_dump(mode="json")
    result["players"] = enriched_players
    return result


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
    enriched_players = await lobby_manager.get_enriched_players(lobby.players)
    lobby_payload = lobby.model_dump(mode="json")
    lobby_payload["players"] = enriched_players
    
    await redis_client.publish("gateway:lobby_update", {
        "target_player_id": str(host_id),
        "event_type": "lobby.created",
        "payload": {
            "lobby_id": str(lobby.id),
            "lobby": lobby_payload
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
        
        enriched_players = await lobby_manager.get_enriched_players(lobby.players)
        lobby_payload = lobby.model_dump(mode="json")
        lobby_payload["players"] = enriched_players

        # Send the joining player a full lobby snapshot so they enter the lobby view
        await redis_client.publish("gateway:lobby_update", {
            "target_player_id": str(player_id),
            "event_type": "lobby.created",
            "payload": {
                "lobby_id": lobby_id,
                "lobby": lobby_payload
            }
        })

        # Notify existing players about the new arrival
        for pid in lobby.players:
            if pid != player_id:
                await redis_client.publish("gateway:lobby_update", {
                    "target_player_id": str(pid),
                    "event_type": "lobby.player_joined",
                    "payload": {
                        "lobby_id": lobby_id,
                        "player_id": str(player_id),
                        "players": enriched_players
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
        
        # Notify the player who left
        await redis_client.publish("gateway:lobby_update", {
            "target_player_id": str(player_id),
            "event_type": "lobby.player_left",
            "payload": {
                "lobby_id": lobby_id,
                "player_id": str(player_id),
                "is_self": True
            }
        })
        
        # Get updated lobby data
        lobby_data = await redis_client.get_state(f"lobby:{lobby_id}")
        
        # Notify remaining players
        if lobby_data:
            lobby = Lobby(**lobby_data)
            enriched_players = await lobby_manager.get_enriched_players(lobby.players)
            for pid in lobby.players:
                await redis_client.publish("gateway:lobby_update", {
                    "target_player_id": str(pid),
                    "event_type": "lobby.player_left",
                    "payload": {
                        "lobby_id": lobby_id,
                        "player_id": str(player_id),
                        "players": enriched_players
                    }
                })


async def handle_lobby_ready(data: dict):
    """Handle ready status change."""
    player_id = UUID(data["player_id"])
    lobby_id = data["lobby_id"]
    ready = data.get("ready", True)
    
    await lobby_manager.set_ready(lobby_id, player_id, ready)
    
    # Check if all ready
    async with redis_client.lock(f"lobby_ready_check:{lobby_id}", timeout=5) as acquired:
        if not acquired:
            return
            
        all_ready = await lobby_manager.is_lobby_ready(lobby_id)
        
        if all_ready:
            # Prevent duplicate session creation by checking lobby status
            lobby_data = await redis_client.get_state(f"lobby:{lobby_id}")
            if lobby_data and lobby_data.get("is_ready"):
                return # Already processing ready state
                
            # Set is_ready to True
            if lobby_data:
                lobby_data["is_ready"] = True
                await redis_client.set_state(f"lobby:{lobby_id}", lobby_data, expire=3600)
                
            # Emit lobby ready event
            event = Event(
                type=EventType.LOBBY_READY,
                payload={"lobby_id": lobby_id}
            )
            await event_store.append(f"lobby:{lobby_id}", event)
            
            # Notify all players
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
                # Using pub/sub here is ok if GameSession handles it idempotently, but enqueue is safer
                await redis_client.publish("session:create_from_lobby", {
                    "lobby_id": lobby_id,
                    "players": [str(p) for p in lobby.players],
                    "game_mode": lobby.game_mode.value
                })

                # Delete lobby immediately after session is triggered
                await redis_client.delete_state(f"lobby:{lobby_id}")
                for pid in lobby.players:
                    await redis_client.redis.delete(f"player:{pid}:lobby_id")
                    await redis_client.delete_state(f"lobby:{lobby_id}:ready:{pid}")


async def handle_create_from_match(data: dict):
    """Create a lobby automatically from a match."""
    match_id = data["match_id"]
    players = [UUID(p) for p in data["players"]]
    game_mode = GameMode(data.get("game_mode", "casual"))
    
    if not players:
        return
        
    host_id = players[0]
    
    # Create the lobby
    lobby = await lobby_manager.create_lobby(
        host_id=host_id,
        name=f"Match {match_id[:8]}",
        game_mode=game_mode,
        max_players=len(players),
        settings={"match_id": match_id}
    )
    
    # Force add all other players to the lobby locally and in redis
    for player_id in players[1:]:
        lobby.players.append(player_id)
        await redis_client.set_state(
            f"player:{player_id}:status",
            {"status": PlayerStatus.IN_LOBBY.value, "lobby_id": str(lobby.id)},
            expire=300
        )
        await redis_client.redis.set(f"player:{player_id}:lobby_id", str(lobby.id))
        
    # Save back to Redis
    await redis_client.set_state(
        f"lobby:{lobby.id}",
        lobby.model_dump(mode="json"),
        expire=3600
    )
    
    # Emit event
    event = Event(
        type=EventType.LOBBY_CREATED,
        payload={
            "lobby_id": str(lobby.id),
            "host_id": str(host_id),
            "name": lobby.name,
            "match_id": match_id
        }
    )
    await event_store.append(f"lobby:{lobby.id}", event)
    
    # Notify all players in match
    enriched_players = await lobby_manager.get_enriched_players(lobby.players)
    lobby_payload = lobby.model_dump(mode="json")
    lobby_payload["players"] = enriched_players
    
    for player_id in players:
        await redis_client.publish("gateway:lobby_update", {
            "target_player_id": str(player_id),
            "event_type": "lobby.created",
            "payload": {
                "lobby_id": str(lobby.id),
                "lobby": lobby_payload
            }
        })

async def handle_player_disconnected(player_id: str):
    """Handle a player disconnect event."""
    lobby_id_bytes = await redis_client.redis.get(f"player:{player_id}:lobby_id")
    if lobby_id_bytes:
        lobby_id = lobby_id_bytes
        await handle_lobby_leave({"player_id": player_id, "lobby_id": lobby_id})


async def process_task_queue(queue_name: str, handler_func):
    """Consume a specific task queue and process it."""
    while True:
        try:
            task = await redis_client.dequeue_task(queue_name, timeout=1)
            if task:
                await handler_func(task)
        except Exception as e:
            print(f"Error processing {queue_name}: {e}")
            await asyncio.sleep(1)

async def subscribe_to_requests():
    """Subscribe to lobby requests via task queues."""
    queues_handlers = {
        "task:lobby:create": handle_lobby_create,
        "task:lobby:join": handle_lobby_join,
        "task:lobby:leave": handle_lobby_leave,
        "task:lobby:ready": handle_lobby_ready,
        "task:lobby:create_from_match": handle_create_from_match
    }
    
    # Start a background loop for each task queue
    for queue_name, handler in queues_handlers.items():
        asyncio.create_task(process_task_queue(queue_name, handler))

async def subscribe_to_disconnects():
    """Subscribe to player disconnect events."""
    pubsub = redis_client.redis.pubsub()
    await pubsub.psubscribe("stream:player:*")
    async for message in pubsub.listen():
        if message["type"] == "pmessage":
            try:
                data = json.loads(message["data"])
                if data.get("type") == EventType.PLAYER_DISCONNECTED.value:
                    player_id = data.get("payload", {}).get("player_id")
                    if player_id:
                        await handle_player_disconnected(player_id)
            except Exception as e:
                print(f"Error processing disconnect: {e}")


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    global event_store
    await redis_client.connect()
    event_store = RedisEventStore(redis_client.redis)
    
    # Start background tasks
    asyncio.create_task(subscribe_to_requests())
    asyncio.create_task(subscribe_to_disconnects())
    
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
