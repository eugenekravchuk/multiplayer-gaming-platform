"""
Gateway Service - Main entry point for WebSocket connections.
Handles authentication, connection management, and message routing.
"""
import asyncio
import json
import os
from typing import Dict, Set
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.redis_client import redis_client
from shared.auth import decode_token, TokenData, create_access_token
from shared.types import Player, PlayerStatus
from shared.events import Event, EventType, RedisEventStore


app = FastAPI(title="Gateway Service", version="1.0.0")

# Service URLs
LEADERBOARD_SERVICE_URL = os.getenv("LEADERBOARD_SERVICE_URL", "http://leaderboard:3004")
LOBBY_SERVICE_URL = os.getenv("LOBBY_SERVICE_URL", "http://lobby:3002")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connection management
class ConnectionManager:
    """Manages WebSocket connections for all players."""
    
    def __init__(self):
        self.connections: Dict[UUID, WebSocket] = {}
        self.player_ids: Dict[WebSocket, UUID] = {}
    
    async def connect(self, websocket: WebSocket, player_id: UUID):
        """Accept and store connection."""
        await websocket.accept()
        self.connections[player_id] = websocket
        self.player_ids[websocket] = player_id
        
        # Update player status in distributed state
        await redis_client.set_state(f"player:{player_id}:status", {
            "status": PlayerStatus.ONLINE.value,
            "websocket_id": id(websocket)
        }, expire=300)
        
        print(f"Player {player_id} connected. Total: {len(self.connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove connection."""
        player_id = self.player_ids.get(websocket)
        if player_id:
            del self.connections[player_id]
            del self.player_ids[websocket]
            print(f"Player {player_id} disconnected. Total: {len(self.connections)}")
        return player_id
    
    async def send_to_player(self, player_id: UUID, message: dict):
        """Send message to specific player."""
        if player_id in self.connections:
            try:
                await self.connections[player_id].send_json(message)
            except Exception as e:
                print(f"Error sending to {player_id}: {e}")
    
    async def broadcast(self, message: dict, exclude: Set[UUID] = None):
        """Broadcast to all or exclude some players."""
        exclude = exclude or set()
        for player_id, websocket in self.connections.items():
            if player_id not in exclude:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    print(f"Error broadcasting to {player_id}: {e}")


manager = ConnectionManager()
event_store: RedisEventStore = None


# Proxy endpoints
async def proxy_request(url: str, request: Request):
    """Generic proxy for HTTP requests."""
    async with httpx.AsyncClient() as client:
        method = request.method
        content = await request.body()
        headers = dict(request.headers)
        # Remove host header to avoid issues with target service
        headers.pop("host", None)
        
        try:
            response = await client.request(
                method,
                url,
                content=content,
                headers=headers,
                params=request.query_params,
                timeout=10.0
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except Exception as e:
            print(f"Proxy error: {e}")
            raise HTTPException(status_code=502, detail="Service unreachable")


@app.api_route("/leaderboard/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_leaderboard(path: str, request: Request):
    print(f"DEBUG: Proxying leaderboard request: {path}")
    return await proxy_request(f"{LEADERBOARD_SERVICE_URL}/leaderboard/{path}", request)


@app.api_route("/lobbies/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_lobbies(path: str, request: Request):
    print(f"DEBUG: Proxying lobbies request: {path}")
    return await proxy_request(f"{LOBBY_SERVICE_URL}/lobbies/{path}", request)


@app.api_route("/lobbies", methods=["GET"])
async def proxy_lobbies_root(request: Request):
    return await proxy_request(f"{LOBBY_SERVICE_URL}/lobbies", request)


# HTTP endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "gateway", "connections": len(manager.connections)}


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    player_id: str
    username: str


@app.post("/auth/login", response_model=LoginResponse)
async def login(request: Request, login_data: LoginRequest):
    """Login endpoint - creates or retrieves a player session by unique username."""
    username = login_data.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")

    # Check if username already has an ID assigned
    username_key = f"username:{username.lower()}:id"
    existing_id = await redis_client.redis.get(username_key)
    
    if existing_id:
        player_id = UUID(existing_id)
        # Verify if it matches exactly (optional, for case sensitivity handling)
        stored_username_data = await redis_client.get_state(f"player:{player_id}:username")
        stored_username = stored_username_data.get("username") if stored_username_data else username
    else:
        # Create new unique ID for this username
        player_id = uuid4()
        await redis_client.redis.set(username_key, str(player_id))
        # Store metadata
        await redis_client.set_state(f"player:{player_id}:username", {"username": username})
    
    token = create_access_token({
        "sub": str(player_id),
        "username": username
    })
    
    return LoginResponse(
        token=token,
        player_id=str(player_id),
        username=username
    )


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket connection handler."""
    token = websocket.query_params.get("token")
    
    # Authenticate
    token_data = decode_token(token) if token else None
    if not token_data or not token_data.user_id:
        await websocket.accept()
        await websocket.send_json({"type": "error", "data": {"message": "Authentication required"}})
        await websocket.close(code=4001, reason="Authentication required")
        return
    
    player_id = token_data.user_id
    
    # Connect
    await manager.connect(websocket, player_id)
    
    # Emit connected event
    try:
        event = Event(
            type=EventType.PLAYER_CONNECTED,
            payload={"player_id": str(player_id), "username": token_data.username}
        )
        await event_store.append(f"player:{player_id}", event)
    except Exception as e:
        print(f"Event store error (non-fatal): {e}")
    
    # Send welcome message
    await manager.send_to_player(player_id, {
        "type": "connected",
        "data": {"player_id": str(player_id), "message": "Welcome to Gaming Platform"}
    })
    
    try:
        while True:
            # Receive message
            raw_message = await websocket.receive_text()
            
            try:
                message = json.loads(raw_message)
                await handle_message(player_id, message)
            except json.JSONDecodeError:
                await manager.send_to_player(player_id, {
                    "type": "error",
                    "data": {"message": "Invalid JSON"}
                })
                
    except WebSocketDisconnect:
        player_id = manager.disconnect(websocket)
        if player_id:
            # Emit disconnected event
            event = Event(
                type=EventType.PLAYER_DISCONNECTED,
                payload={"player_id": str(player_id)}
            )
            await event_store.append(f"player:{player_id}", event)
            await redis_client.delete_state(f"player:{player_id}:status")


async def handle_message(player_id: UUID, message: dict):
    """Route messages to appropriate services."""
    msg_type = message.get("type")
    data = message.get("data", {})
    
    # Route to appropriate service
    if msg_type == "matchmaking.join":
        await handle_matchmaking_join(player_id, data)
    elif msg_type == "matchmaking.cancel":
        await handle_matchmaking_cancel(player_id)
    elif msg_type == "lobby.create":
        await handle_lobby_create(player_id, data)
    elif msg_type == "lobby.join":
        await handle_lobby_join(player_id, data)
    elif msg_type == "lobby.leave":
        await handle_lobby_leave(player_id, data)
    elif msg_type == "lobby.ready":
        await handle_lobby_ready(player_id, data)
    elif msg_type == "game.action":
        await handle_game_action(player_id, data)
    elif msg_type == "chat.message":
        await handle_chat_message(player_id, data)
    elif msg_type == "chat.join":
        await handle_chat_join(player_id, data)
    else:
        await manager.send_to_player(player_id, {
            "type": "error",
            "data": {"message": f"Unknown message type: {msg_type}"}
        })


# Message handlers that publish to Redis for other services
async def handle_matchmaking_join(player_id: UUID, data: dict):
    """Forward matchmaking request."""
    await redis_client.publish("matchmaking:requests", {
        "player_id": str(player_id),
        "game_mode": data.get("game_mode", "casual"),
        "rating": data.get("rating", 1000)
    })
    await manager.send_to_player(player_id, {
        "type": "matchmaking.queued",
        "data": {"message": "Added to matchmaking queue"}
    })


async def handle_matchmaking_cancel(player_id: UUID):
    """Cancel matchmaking."""
    await redis_client.publish("matchmaking:cancel", {
        "player_id": str(player_id)
    })


async def handle_lobby_create(player_id: UUID, data: dict):
    """Forward lobby creation."""
    await redis_client.publish("lobby:create", {
        "player_id": str(player_id),
        "name": data.get("name", "New Lobby"),
        "game_mode": data.get("game_mode", "casual"),
        "max_players": data.get("max_players", 8)
    })


async def handle_lobby_join(player_id: UUID, data: dict):
    """Forward lobby join request."""
    await redis_client.publish("lobby:join", {
        "player_id": str(player_id),
        "lobby_id": data.get("lobby_id")
    })


async def handle_lobby_leave(player_id: UUID, data: dict):
    """Forward lobby leave request."""
    await redis_client.publish("lobby:leave", {
        "player_id": str(player_id),
        "lobby_id": data.get("lobby_id")
    })


async def handle_lobby_ready(player_id: UUID, data: dict):
    """Forward ready status."""
    await redis_client.publish("lobby:ready", {
        "player_id": str(player_id),
        "lobby_id": data.get("lobby_id"),
        "ready": data.get("ready", True)
    })


async def handle_game_action(player_id: UUID, data: dict):
    """Forward game action."""
    await redis_client.publish("game:action", {
        "player_id": str(player_id),
        "session_id": data.get("session_id"),
        "action": data.get("action")
    })


async def handle_chat_message(player_id: UUID, data: dict):
    """Forward chat message."""
    await redis_client.publish("chat:message", {
        "sender_id": str(player_id),
        "channel_id": data.get("channel_id", "global"),
        "content": data.get("content")
    })


async def handle_chat_join(player_id: UUID, data: dict):
    """Forward chat channel join."""
    await redis_client.publish("chat:join", {
        "player_id": str(player_id),
        "channel_id": data.get("channel_id")
    })


# Subscribe to service responses and forward to players
async def subscribe_to_service_responses():
    """Subscribe to Redis channels and forward to WebSocket clients."""
    channels = [
        "gateway:match_found",
        "gateway:lobby_update",
        "gateway:game_event",
        "gateway:chat_message",
        "gateway:notification",
        "gateway:error"
    ]
    
    pubsub = await redis_client.subscribe(*channels)
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                target_player = data.get("target_player_id")
                
                if target_player:
                    await manager.send_to_player(UUID(target_player), {
                        "type": data.get("event_type"),
                        "data": data.get("payload")
                    })
                elif data.get("broadcast"):
                    await manager.broadcast({
                        "type": data.get("event_type"),
                        "data": data.get("payload")
                    })
            except Exception as e:
                print(f"Error processing service response: {e}")


@app.on_event("startup")
async def startup():
    """Initialize connections on startup."""
    global event_store
    await redis_client.connect()
    event_store = RedisEventStore(redis_client.redis)
    
    # Start background task for service responses
    asyncio.create_task(subscribe_to_service_responses())
    
    # Register this gateway instance
    await redis_client.register_service(
        "gateway", 
        os.getenv("HOSTNAME", "gateway-1"),
        "0.0.0.0", 
        int(os.getenv("PORT", 3000))
    )
    
    print("Gateway Service started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await redis_client.disconnect()
    print("Gateway Service shutdown")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)
