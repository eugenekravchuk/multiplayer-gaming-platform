"""Redis client utilities."""
import json
import redis.asyncio as redis
from typing import Optional, Any
import os


class RedisClient:
    """Singleton Redis client wrapper."""
    _instance: Optional['RedisClient'] = None
    _redis: Optional[redis.Redis] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def connect(self, url: str = None):
        """Connect to Redis."""
        if url is None:
            url = os.getenv("REDIS_URL", "redis://localhost:6379")
        
        if self._redis is None:
            self._redis = await redis.from_url(url, decode_responses=True)
        return self._redis
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()
            self._redis = None
    
    @property
    def redis(self) -> redis.Redis:
        """Get Redis client."""
        if self._redis is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._redis
    
    # Pub/Sub helpers
    async def publish(self, channel: str, message: Any) -> None:
        """Publish message to channel."""
        if isinstance(message, (dict, list)):
            message = json.dumps(message)
        await self.redis.publish(channel, message)
    
    async def subscribe(self, *channels: str):
        """Subscribe to channels and return pubsub object."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(*channels)
        return pubsub
    
    # Distributed state helpers
    async def set_state(self, key: str, value: Any, expire: Optional[int] = None) -> None:
        """Set distributed state."""
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await self.redis.set(key, value, ex=expire)
    
    async def get_state(self, key: str) -> Optional[Any]:
        """Get distributed state."""
        value = await self.redis.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None
    
    async def delete_state(self, key: str) -> None:
        """Delete distributed state."""
        await self.redis.delete(key)
    
    # Service discovery helpers
    async def register_service(self, service_name: str, instance_id: str, 
                               host: str, port: int, ttl: int = 30) -> None:
        """Register service instance for service discovery."""
        key = f"services:{service_name}:{instance_id}"
        value = json.dumps({"host": host, "port": port, "registered_at": datetime.utcnow().isoformat()})
        await self.redis.setex(key, ttl, value)
    
    async def discover_service(self, service_name: str) -> Optional[dict]:
        """Discover a service instance (round-robin)."""
        pattern = f"services:{service_name}:*"
        keys = []
        async for key in self.redis.scan_iter(match=pattern):
            keys.append(key)
        
        if not keys:
            return None
        
        # Simple round-robin: pick first available
        key = keys[0]
        value = await self.redis.get(key)
        return json.loads(value) if value else None


from datetime import datetime


# Global Redis client instance
redis_client = RedisClient()
