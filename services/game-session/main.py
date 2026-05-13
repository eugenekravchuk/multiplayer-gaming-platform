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
from shared.types import GameSession, GameState, PlayerStatus, GameMode
from shared.events import Event, EventType, RedisEventStore


app = FastAPI(title="Game Session Service", version="1.0.0")


class GameSessionManager:
    """Manages game sessions with distributed state."""
    
    def __init__(self):
        self.sessions: Dict[str, GameSession] = {}
        self.player_sessions: Dict[str, str] = {} # player_id -> session_id
    
    async def create_session(self, match_id: UUID, players: list[UUID], game_mode: GameMode = GameMode.CASUAL) -> GameSession:
        """Create a new game session."""
        session_id = uuid4()
        
        # Initialize game state
        game_state = GameState(
            session_id=session_id,
            players={pid: {"score": 0} for pid in players},
            game_data={"round": 1, "status": "countdown", "moves": {}}
        )
        
        session = GameSession(
            id=session_id,
            match_id=match_id,
            players=players,
            game_mode=game_mode,
            state=game_state
        )
        
        # Store in Redis (distributed state)
        await redis_client.set_state(
            f"session:{session_id}",
            session.model_dump(mode="json"),
            expire=3600
        )
        
        self.sessions[str(session_id)] = session
        for player_id in players:
            self.player_sessions[str(player_id)] = str(session_id)
        
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

    async def broadcast_session_state(self, session: GameSession, action_type: str, player_id: Optional[UUID] = None):
        """Broadcast session state to all players and sync channel."""
        session_id = str(session.id)
        
        # Save to Redis
        await redis_client.set_state(
            f"session:{session_id}",
            session.model_dump(mode="json"),
            expire=3600
        )
        
        # Sync channel
        await redis_client.publish(f"session:{session_id}:state", {
            "session_id": session_id,
            "version": session.state.version,
            "state": session.state.model_dump(mode="json"),
            "action": {
                "player_id": str(player_id) if player_id else "system",
                "type": action_type
            }
        })

        # Notify players via gateway
        for pid in session.players:
            await redis_client.publish("gateway:game_event", {
                "target_player_id": str(pid),
                "event_type": "game.state_update",
                "payload": {
                    "session_id": session_id,
                    "state": session.state.model_dump(mode="json"),
                    "last_action": {
                        "player_id": str(player_id) if player_id else "system",
                        "type": action_type
                    }
                }
            })

    async def start_countdown(self, session_id: str, delay: int = 3):
        """Start countdown for the next round."""
        await asyncio.sleep(delay)
        session = await self.get_session(session_id)
        if not session or session.status == "ended":
            return

        session.state.game_data["status"] = "in_progress"
        session.state.game_data["moves"] = {}
        session.state.version += 1
        session.state.timestamp = datetime.utcnow()
        
        await self.broadcast_session_state(session, "countdown_finished")
    
    async def update_state(self, session_id: str, player_id: UUID, 
                          action: dict) -> Optional[GameState]:
        """Update game state based on player action."""
        session = await self.get_session(session_id)
        if not session or session.status == "ended":
            return None
        
        action_type = action.get("type")
        
        if action_type == "rps_move":
            if session.state.game_data.get("status") != "in_progress":
                return None
            
            move = action.get("move")
            if move not in ["rock", "paper", "scissors"]:
                return None
            
            # Store move
            session.state.game_data["moves"][str(player_id)] = move
            
            # If both players have moved, calculate winner
            if len(session.state.game_data["moves"]) == 2:
                p1_id, p2_id = session.players
                m1 = session.state.game_data["moves"][str(p1_id)]
                m2 = session.state.game_data["moves"][str(p2_id)]
                
                winner_id = None
                if m1 == m2:
                    winner_id = None # Tie
                elif (m1 == "rock" and m2 == "scissors") or \
                     (m1 == "paper" and m2 == "rock") or \
                     (m1 == "scissors" and m2 == "paper"):
                    winner_id = p1_id
                else:
                    winner_id = p2_id
                
                if winner_id:
                    session.state.players[winner_id]["score"] += 1
                
                session.state.game_data["last_round_winner"] = str(winner_id) if winner_id else "tie"
                session.state.game_data["status"] = "round_finished"
                
                # Check for game winner (3 wins)
                game_winner = None
                for pid in session.players:
                    if session.state.players[pid]["score"] >= 3:
                        game_winner = pid
                        break
                
                if game_winner:
                    session.state.game_data["status"] = "game_finished"
                    session.state.game_data["winner"] = str(game_winner)
                    session.state.version += 1
                    session.state.timestamp = datetime.utcnow()
                    await self.broadcast_session_state(session, "game_finished", player_id)
                    await self.end_session(session_id, game_winner)
                    return session.state
                else:
                    session.state.game_data["round"] += 1
                    asyncio.create_task(self.start_countdown(session_id, 3))
        
        # Increment version and update timestamp
        session.state.version += 1
        session.state.timestamp = datetime.utcnow()
        
        await self.broadcast_session_state(session, action_type, player_id)
        
        return session.state
    
    async def end_session(self, session_id: str, winner_id: Optional[UUID] = None) -> bool:
        """End a game session."""
        session = await self.get_session(session_id)
        if not session or session.status == "ended":
            return False
        
        session.status = "ended"
        session.ended_at = datetime.utcnow()
        session.state.game_data["status"] = "game_finished"
        session.state.game_data["winner"] = str(winner_id) if winner_id else None
        
        # Calculate leaderboard rating changes
        if winner_id and len(session.players) == 2:
            p1_id, p2_id = session.players
            loser_id = p2_id if winner_id == p1_id else p1_id
            
            winner_score = session.state.players[winner_id]["score"]
            loser_score = session.state.players[loser_id]["score"]
            diff = abs(winner_score - loser_score)
            
            winner_rating_change = 10 * diff
            loser_rating_change = -5 * diff
            
            print(f"DEBUG: Ending session {session_id}. Winner: {winner_id}, Diff: {diff}")
            
            await redis_client.publish("leaderboard:update", {
                "player_id": str(winner_id),
                "rating_change": winner_rating_change,
                "win": True,
                "category": session.game_mode.value
            })
            await redis_client.publish("leaderboard:update", {
                "player_id": str(loser_id),
                "rating_change": loser_rating_change,
                "win": False,
                "category": session.game_mode.value
            })

        # Save final state
        await redis_client.set_state(
            f"session:{session_id}",
            session.model_dump(mode="json"),
            expire=3600  # Keep for an hour after ending
        )
        
        # Update player statuses
        for player_id in session.players:
            if str(player_id) in self.player_sessions:
                del self.player_sessions[str(player_id)]
            await redis_client.set_state(
                f"player:{player_id}:status",
                {"status": PlayerStatus.ONLINE.value}
            )
        
        # Remove from local cache
        if session_id in self.sessions:
            del self.sessions[session_id]
            
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
                "score": data.get("score", 0)
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
    game_mode = GameMode(data.get("game_mode", "casual"))
    match_id = uuid4()  # Create new match
    
    # Create session
    session = await session_manager.create_session(match_id, players, game_mode)
    
    # Start countdown task
    asyncio.create_task(session_manager.start_countdown(str(session.id), 3))
    
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


async def handle_player_disconnected(player_id: str):
    """Handle a player disconnect event."""
    session_id = session_manager.player_sessions.get(player_id)
    if session_id:
        session = await session_manager.get_session(session_id)
        if session and session.status == "active":
            # Find the remaining player
            remaining_players = [p for p in session.players if str(p) != player_id]
            winner_id = remaining_players[0] if remaining_players else None
            
            # End the session and award the win
            await session_manager.end_session(session_id, winner_id)
            
            # Update state to reflect game finish due to disconnect
            session.state.game_data["status"] = "game_finished"
            session.state.game_data["winner"] = str(winner_id) if winner_id else None
            session.state.game_data["finish_reason"] = "disconnect"
            session.state.version += 1
            session.state.timestamp = datetime.utcnow()
            
            await session_manager.broadcast_session_state(session, "player_disconnected", UUID(player_id))


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
    asyncio.create_task(subscribe_to_disconnects())
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
