"""
Matchmaking Service - Handles player matchmaking with skill-based matching.
Uses Redis pub/sub for real-time matchmaking requests.
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
from shared.types import MatchRequest, Match, GameMode
from shared.events import Event, EventType, RedisEventStore


app = FastAPI(title="Matchmaking Service", version="1.0.0")

# Matchmaking queue: game_mode -> list of requests
class MatchmakingQueue:
    """Manages matchmaking queues per game mode."""
    
    def __init__(self):
        self.queues: Dict[GameMode, List[MatchRequest]] = {
            GameMode.CASUAL: [],
            GameMode.RANKED: [],
            GameMode.TOURNAMENT: [],
            GameMode.CUSTOM: []
        }
        self.active_searches: Dict[str, MatchRequest] = {}  # player_id -> request
    
    def add_request(self, request: MatchRequest) -> bool:
        """Add player to matchmaking queue."""
        player_id_str = str(request.player_id)
        
        # Remove from queue if already searching
        if player_id_str in self.active_searches:
            self.remove_request(player_id_str)
        
        self.queues[request.game_mode].append(request)
        self.active_searches[player_id_str] = request
        
        print(f"Player {request.player_id} joined {request.game_mode} queue. Queue size: {len(self.queues[request.game_mode])}")
        return True
    
    def remove_request(self, player_id: str) -> bool:
        """Remove player from matchmaking."""
        if player_id not in self.active_searches:
            return False
        
        request = self.active_searches[player_id]
        if request in self.queues[request.game_mode]:
            self.queues[request.game_mode].remove(request)
        
        del self.active_searches[player_id]
        print(f"Player {player_id} removed from matchmaking")
        return True
    
    def get_queue(self, game_mode: GameMode) -> List[MatchRequest]:
        """Get queue for game mode."""
        return self.queues[game_mode]


queue = MatchmakingQueue()
event_store: RedisEventStore = None


class MatchmakingAlgorithm:
    """Skill-based matchmaking algorithm."""
    
    # Rating difference thresholds ( widen over time )
    RATING_THRESHOLDS = [50, 100, 200, 400, 1000]
    WAIT_TIME_MULTIPLIERS = [0, 10, 20, 30, 60]  # seconds
    
    @staticmethod
    def can_match(p1: MatchRequest, p2: MatchRequest) -> bool:
        """Check if two players can be matched."""
        if p1.game_mode != p2.game_mode:
            return False
        
        # Check rating difference based on wait time
        wait_time = (datetime.utcnow() - min(p1.created_at, p2.created_at)).total_seconds()
        
        for i, threshold in enumerate(MatchmakingAlgorithm.RATING_THRESHOLDS):
            if wait_time >= MatchmakingAlgorithm.WAIT_TIME_MULTIPLIERS[i]:
                max_diff = threshold
            else:
                break
        
        rating_diff = abs(p1.rating - p2.rating)
        return rating_diff <= max_diff
    
    @staticmethod
    def find_matches(game_mode: GameMode, players_per_match: int = 2) -> List[List[MatchRequest]]:
        """Find compatible player groups."""
        waiting = queue.get_queue(game_mode).copy()
        matches = []
        used = set()
        
        for player in waiting:
            if str(player.player_id) in used:
                continue
            
            # Find compatible players
            group = [player]
            for other in waiting:
                if len(group) >= players_per_match:
                    break
                
                other_id = str(other.player_id)
                if (other_id not in used
                        and other_id != str(player.player_id)
                        and MatchmakingAlgorithm.can_match(player, other)):
                    group.append(other)
                    used.add(other_id)
            
            if len(group) >= 2:  # Minimum 2 players
                matches.append(group)
                used.add(str(player.player_id))
                
                # Remove matched players from queue
                for p in group:
                    queue.remove_request(str(p.player_id))
        
        return matches


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    queue_sizes = {mode.value: len(queue.get_queue(mode)) for mode in GameMode}
    return {
        "status": "healthy", 
        "service": "matchmaking",
        "active_searches": len(queue.active_searches),
        "queues": queue_sizes
    }


@app.get("/stats")
async def get_stats():
    """Get matchmaking statistics."""
    return {
        "queues": {
            mode.value: [
                {
                    "player_id": str(req.player_id),
                    "rating": req.rating,
                    "wait_time": (datetime.utcnow() - req.created_at).total_seconds()
                }
                for req in queue.get_queue(mode)
            ]
            for mode in GameMode
        }
    }


async def handle_matchmaking_request(data: dict):
    """Process matchmaking join request."""
    player_id = UUID(data["player_id"])
    game_mode = GameMode(data.get("game_mode", "casual"))
    rating = data.get("rating", 1000)
    
    request = MatchRequest(
        player_id=player_id,
        game_mode=game_mode,
        rating=rating,
        region=data.get("region", "default")
    )
    
    # Emit event
    event = Event(
        type=EventType.MATCHMAKING_JOINED,
        payload={
            "player_id": str(player_id),
            "game_mode": game_mode.value,
            "rating": rating
        }
    )
    await event_store.append(f"matchmaking:{player_id}", event)
    
    # Add to queue
    queue.add_request(request)


async def handle_matchmaking_cancel(data: dict):
    """Process matchmaking cancel request."""
    player_id = data["player_id"]
    queue.remove_request(player_id)
    
    event = Event(
        type=EventType.MATCHMAKING_CANCELLED,
        payload={"player_id": player_id}
    )
    await event_store.append(f"matchmaking:{player_id}", event)


async def create_match(players: List[MatchRequest]) -> Match:
    """Create a match from matched players."""
    match_id = uuid4()
    
    match = Match(
        id=match_id,
        players=[p.player_id for p in players],
        game_mode=players[0].game_mode
    )
    
    # Store match in Redis
    await redis_client.set_state(f"match:{match_id}", match.model_dump(mode="json"), expire=3600)
    
    # Emit match found event
    event = Event(
        type=EventType.MATCH_FOUND,
        payload={
            "match_id": str(match_id),
            "players": [str(p.player_id) for p in players],
            "game_mode": players[0].game_mode.value
        }
    )
    await event_store.append(f"match:{match_id}", event)
    
    # Request lobby creation automatically
    await redis_client.publish("lobby:create_from_match", {
        "match_id": str(match_id),
        "players": [str(p.player_id) for p in players],
        "game_mode": players[0].game_mode.value
    })
    
    # Notify players via gateway
    for player in players:
        await redis_client.publish("gateway:match_found", {
            "target_player_id": str(player.player_id),
            "event_type": "match.found",
            "payload": {
                "match_id": str(match_id),
                "players": [str(p.player_id) for p in players],
                "game_mode": players[0].game_mode.value
            }
        })
    
    print(f"Match {match_id} created with {len(players)} players")
    return match


async def run_matchmaker():
    """Background task: continuously run matchmaking algorithm."""
    while True:
        try:
            for game_mode in [GameMode.CASUAL, GameMode.RANKED]:
                matches = MatchmakingAlgorithm.find_matches(game_mode, players_per_match=2)
                
                for player_group in matches:
                    await create_match(player_group)
            
            await asyncio.sleep(2)  # Run every 2 seconds
            
        except Exception as e:
            print(f"Matchmaking error: {e}")
            await asyncio.sleep(5)


async def subscribe_to_requests():
    """Subscribe to matchmaking requests from Redis."""
    pubsub = await redis_client.subscribe("matchmaking:requests", "matchmaking:cancel")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                channel = message["channel"]
                
                if channel == "matchmaking:requests":
                    await handle_matchmaking_request(data)
                elif channel == "matchmaking:cancel":
                    await handle_matchmaking_cancel(data)
                    
            except Exception as e:
                print(f"Error processing request: {e}")


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    global event_store
    await redis_client.connect()
    event_store = RedisEventStore(redis_client.redis)
    
    # Start background tasks
    asyncio.create_task(subscribe_to_requests())
    asyncio.create_task(run_matchmaker())
    
    # Register service
    await redis_client.register_service(
        "matchmaking",
        os.getenv("HOSTNAME", "matchmaking-1"),
        "0.0.0.0",
        int(os.getenv("PORT", 3001))
    )
    
    print("Matchmaking Service started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await redis_client.disconnect()
    print("Matchmaking Service shutdown")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3001))
    uvicorn.run(app, host="0.0.0.0", port=port)
