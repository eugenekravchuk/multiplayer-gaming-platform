"""
Matchmaking Service - Handles player matchmaking with skill-based matching.
Uses Redis lists for reliable task distribution and Redis sets/hashes for shared state.
"""
import asyncio
import json
import os
from typing import Dict, List, Optional
from uuid import UUID, uuid4
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.redis_client import redis_client
from shared.types import MatchRequest, Match, GameMode
from shared.events import Event, EventType, RedisEventStore


event_store: RedisEventStore = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    print("Matchmaking Service starting up...", flush=True)
    global event_store
    await redis_client.connect()
    event_store = RedisEventStore(redis_client.redis)
    
    # Start background tasks
    asyncio.create_task(subscribe_to_join_requests())
    asyncio.create_task(subscribe_to_cancel_requests())
    asyncio.create_task(run_matchmaker())
    
    # Register service
    await redis_client.register_service(
        "matchmaking",
        os.getenv("HOSTNAME", str(uuid4())),
        "0.0.0.0",
        int(os.getenv("PORT", 3001))
    )
    print("Matchmaking Service ready and listening for tasks", flush=True)
    
    yield
    
    # Shutdown logic
    await redis_client.disconnect()
    print("Matchmaking Service shutdown", flush=True)


app = FastAPI(title="Matchmaking Service", version="1.0.0", lifespan=lifespan)


class DistributedMatchmakingQueue:
    """Manages matchmaking queues per game mode using Redis."""
    
    async def add_request(self, request: MatchRequest) -> bool:
        player_id_str = str(request.player_id)
        game_mode_str = request.game_mode.value
        
        await self.remove_request(player_id_str)
        
        request_data = {
            "player_id": player_id_str,
            "game_mode": game_mode_str,
            "rating": request.rating,
            "region": request.region,
            "created_at": request.created_at.isoformat()
        }
        await redis_client.redis.hset("matchmaking:active_requests", player_id_str, json.dumps(request_data))
        await redis_client.redis.zadd(f"matchmaking:queue:{game_mode_str}", {player_id_str: request.created_at.timestamp()})
        
        print(f"DEBUG: Added {player_id_str} to {game_mode_str} queue", flush=True)
        return True
    
    async def remove_request(self, player_id: str) -> bool:
        request_data_str = await redis_client.redis.hget("matchmaking:active_requests", player_id)
        if not request_data_str:
            return False
            
        request_data = json.loads(request_data_str)
        game_mode_str = request_data["game_mode"]
        
        await redis_client.redis.zrem(f"matchmaking:queue:{game_mode_str}", player_id)
        await redis_client.redis.hdel("matchmaking:active_requests", player_id)
        
        print(f"DEBUG: Removed {player_id} from matchmaking queue", flush=True)
        return True
    
    async def get_queue(self, game_mode: GameMode) -> List[MatchRequest]:
        game_mode_str = game_mode.value
        player_ids = await redis_client.redis.zrange(f"matchmaking:queue:{game_mode_str}", 0, -1)
        
        if not player_ids:
            return []
            
        requests = []
        for pid in player_ids:
            req_data_str = await redis_client.redis.hget("matchmaking:active_requests", pid)
            if req_data_str:
                req_data = json.loads(req_data_str)
                req = MatchRequest(
                    player_id=UUID(req_data["player_id"]),
                    game_mode=GameMode(req_data["game_mode"]),
                    rating=req_data["rating"],
                    region=req_data["region"]
                )
                req.created_at = datetime.fromisoformat(req_data["created_at"])
                requests.append(req)
            else:
                await redis_client.redis.zrem(f"matchmaking:queue:{game_mode_str}", pid)
                
        return requests


queue = DistributedMatchmakingQueue()


class MatchmakingAlgorithm:
    RATING_THRESHOLDS = [50, 100, 200, 400, 1000]
    WAIT_TIME_MULTIPLIERS = [0, 10, 20, 30, 60]
    
    @staticmethod
    def can_match(p1: MatchRequest, p2: MatchRequest) -> bool:
        if p1.game_mode != p2.game_mode:
            return False
        
        now = datetime.utcnow()
        wait_time = max(0, (now - min(p1.created_at, p2.created_at)).total_seconds())
        
        max_diff = MatchmakingAlgorithm.RATING_THRESHOLDS[0]
        for i, threshold in enumerate(MatchmakingAlgorithm.RATING_THRESHOLDS):
            if wait_time >= MatchmakingAlgorithm.WAIT_TIME_MULTIPLIERS[i]:
                max_diff = threshold
            else:
                break
        
        rating_diff = abs(p1.rating - p2.rating)
        can_match = rating_diff <= max_diff
        return can_match
    
    @staticmethod
    async def find_matches(game_mode: GameMode, players_per_match: int = 2) -> List[List[MatchRequest]]:
        waiting = await queue.get_queue(game_mode)
        if len(waiting) >= 2:
            print(f"DEBUG: Processing {len(waiting)} players in {game_mode.value} queue", flush=True)
            
        matches = []
        used = set()
        
        for player in waiting:
            if str(player.player_id) in used:
                continue
            
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
            
            if len(group) >= players_per_match:
                matches.append(group)
                for p in group:
                    used.add(str(p.player_id))
                    await queue.remove_request(str(p.player_id))
        
        return matches


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "matchmaking"}


async def handle_matchmaking_request(data: dict):
    player_id = UUID(data["player_id"])
    game_mode = GameMode(data.get("game_mode", "casual"))
    rating = data.get("rating", 1000)
    
    request = MatchRequest(
        player_id=player_id,
        game_mode=game_mode,
        rating=rating,
        region=data.get("region", "default")
    )
    
    event = Event(
        type=EventType.MATCHMAKING_JOINED,
        payload={"player_id": str(player_id), "game_mode": game_mode.value, "rating": rating}
    )
    await event_store.append(f"matchmaking:{player_id}", event)
    await queue.add_request(request)


async def handle_matchmaking_cancel(data: dict):
    player_id = data["player_id"]
    await queue.remove_request(player_id)
    
    event = Event(
        type=EventType.MATCHMAKING_CANCELLED,
        payload={"player_id": player_id}
    )
    await event_store.append(f"matchmaking:{player_id}", event)


async def create_match(players: List[MatchRequest]) -> Match:
    match_id = uuid4()
    match = Match(
        id=match_id,
        players=[p.player_id for p in players],
        game_mode=players[0].game_mode
    )
    
    await redis_client.set_state(f"match:{match_id}", match.model_dump(mode="json"), expire=3600)
    
    event = Event(
        type=EventType.MATCH_FOUND,
        payload={
            "match_id": str(match_id),
            "players": [str(p.player_id) for p in players],
            "game_mode": players[0].game_mode.value
        }
    )
    await event_store.append(f"match:{match_id}", event)
    
    await redis_client.enqueue_task("task:lobby:create_from_match", {
        "match_id": str(match_id),
        "players": [str(p.player_id) for p in players],
        "game_mode": players[0].game_mode.value
    })
    
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
    
    print(f"SUCCESS: Match {match_id} created for {len(players)} players", flush=True)
    return match


async def run_matchmaker():
    print("Matchmaking loop background task started", flush=True)
    while True:
        try:
            for game_mode in [GameMode.CASUAL, GameMode.RANKED]:
                async with redis_client.lock(f"matchmaking_{game_mode.value}", timeout=5, wait=False) as acquired:
                    if acquired:
                        matches = await MatchmakingAlgorithm.find_matches(game_mode, players_per_match=2)
                        for player_group in matches:
                            await create_match(player_group)
            await asyncio.sleep(2)
        except Exception as e:
            print(f"ERROR in run_matchmaker: {e}", flush=True)
            await asyncio.sleep(5)


async def subscribe_to_join_requests():
    print("Task worker: join_requests started", flush=True)
    while True:
        try:
            task = await redis_client.dequeue_task("task:matchmaking:requests", timeout=1)
            if task:
                print(f"DEBUG: Processing join request for {task.get('player_id')}", flush=True)
                await handle_matchmaking_request(task)
        except Exception as e:
            print(f"ERROR in join_requests worker: {e}", flush=True)
            await asyncio.sleep(1)

async def subscribe_to_cancel_requests():
    print("Task worker: cancel_requests started", flush=True)
    while True:
        try:
            task = await redis_client.dequeue_task("task:matchmaking:cancel", timeout=1)
            if task:
                await handle_matchmaking_cancel(task)
        except Exception as e:
            print(f"ERROR in cancel_requests worker: {e}", flush=True)
            await asyncio.sleep(1)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3001))
    uvicorn.run(app, host="0.0.0.0", port=port)
