"""Redis client utilities."""
import json
import os
import asyncio
from typing import Optional, Any, List
from datetime import datetime
from uuid import UUID, uuid4
from contextlib import asynccontextmanager
import redis.asyncio as redis


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
            url = os.getenv("REDIS_URL", "redis://redis:6379")
        
        if self._redis is None:
            print(f"Connecting to Redis at {url}...")
            self._redis = await redis.from_url(url, decode_responses=True)
            # Verify connection
            await self._redis.ping()
            print("Connected to Redis successfully")
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
        
    # Task Queue helpers (for scalable worker distribution)
    async def enqueue_task(self, queue_name: str, task: Any) -> None:
        """Push a task to a Redis list queue."""
        if isinstance(task, (dict, list)):
            task = json.dumps(task)
        await self.redis.lpush(queue_name, task)
        
    async def dequeue_task(self, queue_name: str, timeout: int = 0) -> Optional[dict]:
        """Pop a task from a Redis list queue (blocks for `timeout` seconds)."""
        result = await self.redis.brpop(queue_name, timeout=timeout)
        if result:
            _, task_data = result
            try:
                return json.loads(task_data)
            except json.JSONDecodeError:
                return task_data
        return None

    @asynccontextmanager
    async def lock(self, lock_name: str, timeout: int = 10, wait: bool = True):
        """Distributed lock using Redis SETNX."""
        lock_key = f"lock:{lock_name}"
        lock_id = str(uuid4())
        acquired = False
        try:
            while not acquired:
                acquired = await self.redis.set(lock_key, lock_id, nx=True, ex=timeout)
                if not acquired:
                    if not wait:
                        break
                    await asyncio.sleep(0.1)
            yield acquired
        finally:
            if acquired:
                script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                await self.redis.eval(script, 1, lock_key, lock_id)
    
    async def register_service(self, service_name: str, instance_id: str, 
                               host: str, port: int, ttl: int = 30) -> None:
        """Register service instance for service discovery."""
        key = f"services:{service_name}:{instance_id}"
        value = json.dumps({
            "host": host, 
            "port": port, 
            "registered_at": datetime.utcnow().isoformat()
        })
        await self.redis.setex(key, ttl, value)


# Global Redis client instance
redis_client = RedisClient()
