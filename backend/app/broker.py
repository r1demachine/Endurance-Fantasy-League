"""Асинхронный брокер уведомлений.

Redis pub/sub, если доступен REDIS_URL; иначе — in-memory asyncio-очереди
(одноинстансовый fallback для Render free).
Продюсеры публикуют события, SSE-подписчики получают их в реальном времени.
"""
import asyncio
import json
import os

_redis = None
_local_queues: dict[int, set[asyncio.Queue]] = {}


def _redis_url() -> str | None:
    url = os.getenv("REDIS_URL")
    if url:
        return url
    try:
        from .config import get_settings
        return getattr(get_settings(), "REDIS_URL", None)
    except Exception:
        return None


async def init_broker() -> None:
    global _redis
    url = _redis_url()
    if not url:
        print("📮 Broker: in-memory asyncio (REDIS_URL не задан)")
        return
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(url, decode_responses=True)
        await client.ping()
        _redis = client
        asyncio.create_task(_redis_listener())
        print("📮 Broker: Redis pub/sub")
    except Exception as e:
        _redis = None
        print(f"📮 Broker: fallback in-memory ({type(e).__name__})")


async def _redis_listener() -> None:
    pubsub = _redis.pubsub()
    await pubsub.subscribe("notifications")
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        try:
            data = json.loads(message["data"])
            _dispatch_local(data["user_id"], data)
        except Exception:
            continue


def _dispatch_local(user_id: int, payload: dict) -> None:
    for q in list(_local_queues.get(user_id, set())):
        q.put_nowait(payload)


async def publish(user_id: int, payload: dict) -> None:
    payload = {**payload, "user_id": user_id}
    if _redis is not None:
        try:
            await _redis.publish("notifications", json.dumps(payload))
            return
        except Exception:
            pass
    _dispatch_local(user_id, payload)


def subscribe(user_id: int) -> asyncio.Queue:
    q = asyncio.Queue()
    _local_queues.setdefault(user_id, set()).add(q)
    return q


def unsubscribe(user_id: int, q: asyncio.Queue) -> None:
    subs = _local_queues.get(user_id)
    if subs and q in subs:
        subs.remove(q)