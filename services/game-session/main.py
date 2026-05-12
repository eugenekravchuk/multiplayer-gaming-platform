"""
Game Session Service - Manages game sessions with distributed state.
Uses event sourcing for game state updates and Redis for real-time state sync.
"""
import asyncio
import json
import os
from typing import Dict, Optional, Any
from uuid import UUID, uuid4
from datetime import datetime

from fastapi import FastAPI

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.redis_client import redis_client
from shared.types import GameSession, GameState, PlayerStatus
from shared.events import Event, EventType, RedisEventStore


app = FastAPI(title="Game Session Service", version="1.0.0")


class GameSessionManager:
    """Manages game sessions with distributed state."""
    
    def __init__(self):
        self.sessions: Dict[str, GameSession] = {}
    
    async def create_session(self, match_id: UUID, players: list[UUID]) -> GameSession:
        """Create a new game session."""
        session_id = uuid4()
        
        # Initialize game state
        game_state = GameState(
            session_id=session_id,
            players={pid: {"health": 100, "score": 0, "position": {"x": 0, "y": 0}} for pid in players},
            game_data={"round": 1, "status": "waiting"}
        )
        
        session = GameSession(
            id=session_id,
            match_id=match_id,
            players=players,
            state=game_state
        )
        
        # Store in Redis (distributed state)
        await redis_client.set_state(
            f"session:{session_id}",
            session.model_dump(mode="json"),
            expire=3600
        )
        
        self.sessions[str(session_id)] = session
        
        # Update player statuses
        for player_id in players:
            await redis_client.set_state(
                f"player:{player_id}:status",
                {"status": PlayerStatus.IN_GAME.value, "session_id": str(session_id)}
            )
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[GameSession]:
        """Get session by ID."""
        # Try local cache first
        if session_id in self.sessions:
            return self.sessions[session_id]
        
        # Fall back to Redis
        data = await redis_client.get_state(f"session:{session_id}")
        if data:
            return GameSession(**data)
        return None
    
    async def update_state(self, session_id: str, player_id: UUID, 
                          action: dict) -> Optional[GameState]:
        """Update game state based on player action."""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        # Apply action to game state
        # This is a simplified example - real implementation would have game-specific logic
        action_type = action.get("type")
        
        if action_type == "move":
            position = action.get("position", {})
            session.state.players[player_id]["position"] = position
        
        elif action_type == "attack":
            target = action.get("target")
            damage = action.get("damage", 10)
            if target in session.state.players:
                session.state.players[target]["health"] -= damage
        
        elif action_type == "score":
            points = action.get("points", 0)
            session.state.players[player_id]["score"] += points
        
        # Increment version and update timestamp
        session.state.version += 1
        session.state.timestamp = datetime.utcnow()
        
        # Save to Redis
        await redis_client.set_state(
            f"session:{session_id}",
            session.model_dump(mode="json"),
            expire=3600
        )
        
        # Publish state update for real-time sync
        await redis_client.publish(f"session:{session_id}:state", {
            "session_id": session_id,
            "version": session.state.version,
            "state": session.state.model_dump(mode="json"),
            "action": {
                "player_id": str(player_id),
                "type": action_type
            }
        })
        
        return session.state
    
    async def end_session(self, session_id: str, winner_id: Optional[UUID] = None) -> bool:
        """End a game session."""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.status = "ended"
        session.ended_at = datetime.utcnow()
        session.state.game_data["status"] = "ended"
        session.state.game_data["winner"] = str(winner_id) if winner_id else None
        
        # Save final state
        await redis_client.set_state(
            f"session:{session_id}",
            session.model_dump(mode="json"),
            expire=3600  # Keep for an hour after ending
        )
        
        # Update player statuses
        for player_id in session.players:
            await redis_client.set_state(
                f"player:{player_id}:status",
                {"status": PlayerStatus.ONLINE.value}
            )
        
        return True
    
    async def get_leaderboard(self, session_id: str) -> list[dict]:
        """Get session leaderboard sorted by score."""
        session = await self.get_session(session_id)
        if not session:
            return []
        
        # Sort players by score
        leaderboard = []
        for player_id, data in session.state.players.items():
            leaderboard.append({
                "player_id": str(player_id),
                "score": data.get("score", 0),
                "health": data.get("health", 0)
            })
        
        leaderboard.sort(key=lambda x: x["score"], reverse=True)
        return leaderboard


session_manager = GameSessionManager()
event_store: RedisEventStore = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "game-session",
        "active_sessions": len(session_manager.sessions)
    }


@app.get("/sessions")
async def list_sessions():
    """List all active sessions."""
    result = []
    for session_id, session in session_manager.sessions.items():
        result.append({
            "id": session_id,
            "match_id": str(session.match_id),
            "players": [str(p) for p in session.players],
            "status": session.status,
            "version": session.state.version
        })
    return {"sessions": result}


@app.get("/sessions/{session_id}")
async def get_session_state(session_id: str):
    """Get session state."""
    session = await session_manager.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    
    return {
        "session_id": session_id,
        "status": session.status,
        "state": session.state.model_dump(mode="json")
    }


@app.get("/sessions/{session_id}/leaderboard")
async def get_session_leaderboard(session_id: str):
    """Get session leaderboard."""
    leaderboard = await session_manager.get_leaderboard(session_id)
    return {"leaderboard": leaderboard}


async def handle_create_from_lobby(data: dict):
    """Create session from lobby."""
    lobby_id = data["lobby_id"]
    players = [UUID(p) for p in data["players"]]
    match_id = uuid4()  # Create new match
    
    # Create session
    session = await session_manager.create_session(match_id, players)
    
    # Emit session started event
    event = Event(
        type=EventType.SESSION_STARTED,
        payload={
            "session_id": str(session.id),
            "match_id": str(match_id),
            "lobby_id": lobby_id,
            "players": [str(p) for p in players]
        }
    )
    await event_store.append(f"session:{session.id}", event)
    
    # Notify all players
    for player_id in players:
        await redis_client.publish("gateway:game_event", {
            "target_player_id": str(player_id),
            "event_type": "session.started",
            "payload": {
                "session_id": str(session.id),
                "state": session.state.model_dump(mode="json")
            }
        })


async def handle_game_action(data: dict):
    """Handle game action from player."""
    player_id = UUID(data["player_id"])
    session_id = data["session_id"]
    action = data["action"]
    
    # Update game state
    new_state = await session_manager.update_state(session_id, player_id, action)
    
    if new_state:
        # Emit game state update event
        event = Event(
            type=EventType.GAME_STATE_UPDATE,
            payload={
                "session_id": session_id,
                "version": new_state.version,
                "action_player": str(player_id),
                "action": action
            }
        )
        await event_store.append(f"session:{session_id}", event)
        
        # Notify all players in session
        session = await session_manager.get_session(session_id)
        for pid in session.players:
            await redis_client.publish("gateway:game_event", {
                "target_player_id": str(pid),
                "event_type": "game.state_update",
                "payload": {
                    "session_id": session_id,
                    "state": new_state.model_dump(mode="json"),
                    "last_action": {
                        "player_id": str(player_id),
                        "type": action.get("type")
                    }
                }
            })


async def subscribe_to_requests():
    """Subscribe to session requests."""
    pubsub = await redis_client.subscribe("session:create_from_lobby", "game:action")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                channel = message["channel"]
                
                if channel == "session:create_from_lobby":
                    await handle_create_from_lobby(data)
                elif channel == "game:action":
                    await handle_game_action(data)
                    
            except Exception as e:
                print(f"Error processing session request: {e}")


# State sync: broadcast state updates to all connected clients
async def broadcast_state_updates():
    """Listen for state updates and ensure sync across instances."""
    pubsub = await redis_client.subscribe("session:*:state")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                # State is already distributed via Redis, 
                # but we can add additional sync logic here if needed
            except Exception as e:
                print(f"Error in state sync: {e}")


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    global event_store
    await redis_client.connect()
    event_store = RedisEventStore(redis_client.redis)
    
    # Start background tasks
    asyncio.create_task(subscribe_to_requests())
    asyncio.create_task(broadcast_state_updates())
    
    # Register service
    await redis_client.register_service(
        "game-session",
        os.getenv("HOSTNAME", "game-session-1"),
        "0.0.0.0",
        int(os.getenv("PORT", 3003))
    )
    
    print("Game Session Service started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await redis_client.disconnect()
    print("Game Session Service shutdown")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3003))
    uvicorn.run(app, host="0.0.0.0", port=port)
