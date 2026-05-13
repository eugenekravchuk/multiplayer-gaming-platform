"""
Leaderboard Service - Manages player rankings and scores.
Uses Redis sorted sets for efficient ranking queries.
"""
import asyncio
import json
import os
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.redis_client import redis_client
from shared.types import LeaderboardEntry
from shared.events import Event, EventType, RedisEventStore


app = FastAPI(title="Leaderboard Service", version="1.0.0")


class LeaderboardManager:
    """Manages leaderboards using Redis sorted sets."""
    
    def __init__(self):
        self.leaderboards = {
            "global": "leaderboard:global",
            "casual": "leaderboard:casual",
            "ranked": "leaderboard:ranked",
            "tournament": "leaderboard:tournament"
        }
    
    async def update_score(self, player_id: UUID, username: str, score: int,
                         wins: int = 0, losses: int = 0, 
                         category: str = "global") -> bool:
        """Update player score on leaderboard."""
        key = self.leaderboards.get(category, "leaderboard:global")
        
        # Save username globally
        await redis_client.set_state(f"player:{player_id}:username", {"username": username})
        
        # Add to sorted set (score as value, player_id as member)
        await redis_client.redis.zadd(key, {str(player_id): score})
        
        # Store detailed stats
        stats_key = f"player_stats:{player_id}:{category}"
        await redis_client.set_state(stats_key, {
            "player_id": str(player_id),
            "username": username,
            "score": score,
            "wins": wins,
            "losses": losses,
            "updated_at": datetime.utcnow().isoformat()
        })
        
        return True
    
    async def get_rank(self, player_id: UUID, category: str = "global") -> Optional[int]:
        """Get player rank (1-indexed)."""
        key = self.leaderboards.get(category, "leaderboard:global")
        
        # Get rank (0-indexed, so add 1)
        rank = await redis_client.redis.zrevrank(key, str(player_id))
        if rank is not None:
            return rank + 1
        return None
    
    async def get_top_players(self, category: str = "global", 
                              limit: int = 100) -> List[LeaderboardEntry]:
        """Get top N players from leaderboard."""
        key = self.leaderboards.get(category, "leaderboard:global")
        
        # Get top players with scores (zrevrange for descending order)
        results = await redis_client.redis.zrevrange(
            key, 0, limit - 1, withscores=True
        )
        
        entries = []
        for rank, (player_id, score) in enumerate(results, 1):
            # Get player stats
            stats = await redis_client.get_state(f"player_stats:{player_id}:{category}")
            
            username = "Unknown"
            wins = 0
            losses = 0
            
            if stats:
                username = stats.get("username", "Unknown")
                wins = stats.get("wins", 0)
                losses = stats.get("losses", 0)
            
            # Fallback to global username if unknown
            if username == "Unknown":
                user_data = await redis_client.get_state(f"player:{player_id}:username")
                if user_data:
                    username = user_data.get("username", "Unknown")
            
            entry = LeaderboardEntry(
                player_id=UUID(player_id),
                username=username,
                score=int(score),
                wins=wins,
                losses=losses,
                rank=rank
            )
            entries.append(entry)
        
        return entries
    
    async def get_player_stats(self, player_id: UUID, 
                               category: str = "global") -> Optional[LeaderboardEntry]:
        """Get player leaderboard stats."""
        key = self.leaderboards.get(category, "leaderboard:global")
        
        # Get score
        score = await redis_client.redis.zscore(key, str(player_id))
        if score is None:
            return None
        
        # Get rank
        rank = await self.get_rank(player_id, category)
        
        # Get detailed stats
        stats = await redis_client.get_state(f"player_stats:{player_id}:{category}")
        
        username = "Unknown"
        wins = 0
        losses = 0
        
        if stats:
            username = stats.get("username", "Unknown")
            wins = stats.get("wins", 0)
            losses = stats.get("losses", 0)
            
        # Fallback to global username if unknown
        if username == "Unknown":
            user_data = await redis_client.get_state(f"player:{player_id}:username")
            if user_data:
                username = user_data.get("username", "Unknown")
        
        return LeaderboardEntry(
            player_id=player_id,
            username=username,
            score=int(score),
            wins=wins,
            losses=losses,
            rank=rank
        )
    
    async def get_nearby_players(self, player_id: UUID, category: str = "global",
                                  range_count: int = 5) -> List[LeaderboardEntry]:
        """Get players near the given player's rank."""
        key = self.leaderboards.get(category, "leaderboard:global")
        
        # Get player rank
        rank = await redis_client.redis.zrevrank(key, str(player_id))
        if rank is None:
            return []
        
        # Calculate range
        start = max(0, rank - range_count)
        end = rank + range_count
        
        # Get players in range
        results = await redis_client.redis.zrevrange(
            key, start, end, withscores=True
        )
        
        entries = []
        for i, (pid, score) in enumerate(results, start=1):
            stats = await redis_client.get_state(f"player_stats:{pid}:{category}")
            
            entry = LeaderboardEntry(
                player_id=UUID(pid),
                username=stats.get("username", "Unknown") if stats else "Unknown",
                score=int(score),
                wins=stats.get("wins", 0) if stats else 0,
                losses=stats.get("losses", 0) if stats else 0,
                rank=i
            )
            entries.append(entry)
        
        return entries
    
    async def increment_score(self, player_id: UUID, username: str,
                              points: int, category: str = "global") -> int:
        """Increment player score by points."""
        key = self.leaderboards.get(category, "leaderboard:global")
        
        # Increment in sorted set
        new_score = await redis_client.redis.zincrby(key, points, str(player_id))
        
        # Try to get username if not provided
        if not username or username == "Unknown":
            user_data = await redis_client.get_state(f"player:{player_id}:username")
            if user_data:
                username = user_data.get("username", "Unknown")

        # Update stats
        stats_key = f"player_stats:{player_id}:{category}"
        stats = await redis_client.get_state(stats_key) or {}
        stats["player_id"] = str(player_id)
        stats["username"] = username
        stats["score"] = int(new_score)
        stats["updated_at"] = datetime.utcnow().isoformat()
        await redis_client.set_state(stats_key, stats)
        
        return int(new_score)
    
    async def record_match_result(self, player_id: UUID, username: str,
                                   won: bool, points: int = 0,
                                   category: str = "global") -> dict:
        """Record match result and update score."""
        stats_key = f"player_stats:{player_id}:{category}"
        stats = await redis_client.get_state(stats_key) or {}
        
        # Update wins/losses
        wins = stats.get("wins", 0) + (1 if won else 0)
        losses = stats.get("losses", 0) + (0 if won else 1)
        
        # Calculate new score (base score + win bonus)
        score_change = points + (20 if won else -10)
        new_score = await self.increment_score(player_id, username, score_change, category)
        
        # Update stats
        stats.update({
            "player_id": str(player_id),
            "username": username,
            "score": new_score,
            "wins": wins,
            "losses": losses,
            "updated_at": datetime.utcnow().isoformat()
        })
        await redis_client.set_state(stats_key, stats)
        
        return {
            "player_id": str(player_id),
            "new_score": new_score,
            "wins": wins,
            "losses": losses
        }


leaderboard_manager = LeaderboardManager()
event_store: RedisEventStore = None


# HTTP Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "leaderboard"}


@app.get("/leaderboard/{category}")
async def get_leaderboard(category: str = "global", limit: int = 100):
    """Get leaderboard for category."""
    entries = await leaderboard_manager.get_top_players(category, limit)
    return {
        "category": category,
        "entries": [e.model_dump(mode="json") for e in entries]
    }


@app.get("/leaderboard/{category}/player/{player_id}")
async def get_player_leaderboard_stats(category: str, player_id: str):
    """Get player's leaderboard stats."""
    stats = await leaderboard_manager.get_player_stats(UUID(player_id), category)
    if not stats:
        return {"error": "Player not found in leaderboard"}
    return stats.model_dump(mode="json")


@app.get("/leaderboard/{category}/player/{player_id}/nearby")
async def get_nearby(category: str, player_id: str, range_count: int = 5):
    """Get players near the given player."""
    entries = await leaderboard_manager.get_nearby_players(
        UUID(player_id), category, range_count
    )
    return {
        "category": category,
        "entries": [e.model_dump(mode="json") for e in entries]
    }


# Event handlers
async def handle_score_update(data: dict):
    """Handle score update event."""
    print(f"DEBUG: Received score update: {data}")
    player_id = UUID(data["player_id"])
    rating_change = data.get("rating_change", 0)
    category = data.get("category", "global")
    won = data.get("win", False)
    
    # Get current username if possible
    stats = await redis_client.get_state(f"player_stats:{player_id}:{category}")
    username = stats.get("username", "Unknown") if stats else "Unknown"
    
    # Update wins/losses
    wins = (stats.get("wins", 0) if stats else 0) + (1 if won else 0)
    losses = (stats.get("losses", 0) if stats else 0) + (0 if won else 1)
    
    # Increment score for specific category
    new_score = await leaderboard_manager.increment_score(
        player_id, username, rating_change, category
    )
    
    # Also update global leaderboard
    if category != "global":
        await leaderboard_manager.increment_score(
            player_id, username, rating_change, "global"
        )
    
    # Update detailed stats (wins/losses)
    for cat in set([category, "global"]):
        stats_key = f"player_stats:{player_id}:{cat}"
        updated_stats = await redis_client.get_state(stats_key) or {}
        
        # Recalculate wins/losses for global might be tricky if we don't have total history,
        # but for now we can just increment them too.
        cat_wins = (updated_stats.get("wins", 0)) + (1 if won else 0)
        cat_losses = (updated_stats.get("losses", 0)) + (0 if won else 1)
        
        updated_stats.update({
            "player_id": str(player_id),
            "username": username,
            "wins": cat_wins,
            "losses": cat_losses,
            "updated_at": datetime.utcnow().isoformat()
        })
        await redis_client.set_state(stats_key, updated_stats)
    
    # Emit event
    event = Event(
        type=EventType.SCORE_UPDATED,
        payload={
            "player_id": str(player_id),
            "score": new_score,
            "rating_change": rating_change,
            "category": category
        }
    )
    await event_store.append(f"leaderboard:{player_id}", event)
    
    # Notify player via gateway
    await redis_client.publish("gateway:notification", {
        "target_player_id": str(player_id),
        "event_type": "score.updated",
        "payload": {
            "new_score": new_score,
            "rating_change": rating_change,
            "wins": wins,
            "losses": losses
        }
    })


async def handle_session_ended(data: dict):
    """Handle game session end - update scores."""
    session_id = data.get("session_id")
    results = data.get("results", [])
    category = data.get("category", "ranked")
    
    for result in results:
        player_id = UUID(result["player_id"])
        username = result.get("username", "Unknown")
        won = result.get("won", False)
        points = result.get("points", 0)
        
        update = await leaderboard_manager.record_match_result(
            player_id, username, won, points, category
        )
        
        # Notify player of score update
        await redis_client.publish("gateway:notification", {
            "target_player_id": str(player_id),
            "event_type": "score.updated",
            "payload": {
                "session_id": session_id,
                "new_score": update["new_score"],
                "wins": update["wins"],
                "losses": update["losses"]
            }
        })


async def handle_player_connected(data: dict):
    """Handle player connected event - capture username."""
    player_id = UUID(data["player_id"])
    username = data.get("username")
    if username:
        await redis_client.set_state(f"player:{player_id}:username", {"username": username})


async def subscribe_to_events():
    """Subscribe to score update events."""
    pubsub = await redis_client.subscribe("leaderboard:update", "session:ended")
    
    # Pattern subscribe to capture player connected events from Gateway
    p_pubsub = redis_client.redis.pubsub()
    await p_pubsub.psubscribe("stream:player:*")
    
    async def listen_to_patterns():
        async for message in p_pubsub.listen():
            if message["type"] == "pmessage":
                try:
                    data = json.loads(message["data"])
                    if data.get("type") == EventType.PLAYER_CONNECTED.value:
                        await handle_player_connected(data.get("payload", {}))
                except Exception as e:
                    print(f"Error processing pattern event: {e}")

    asyncio.create_task(listen_to_patterns())
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                channel = message["channel"]
                
                if channel == "leaderboard:update":
                    await handle_score_update(data)
                elif channel == "session:ended":
                    await handle_session_ended(data)
                    
            except Exception as e:
                print(f"Error processing leaderboard event: {e}")


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
        "leaderboard",
        os.getenv("HOSTNAME", "leaderboard-1"),
        "0.0.0.0",
        int(os.getenv("PORT", 3004))
    )
    
    print("Leaderboard Service started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await redis_client.disconnect()
    print("Leaderboard Service shutdown")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3004))
    uvicorn.run(app, host="0.0.0.0", port=port)
