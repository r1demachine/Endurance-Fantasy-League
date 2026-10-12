"""Intervals.icu API client — только per-user (ключ берётся из аккаунта пользователя)."""

import httpx
import logging
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional, Callable, Awaitable
from ..config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

SPORT_XP_MULTIPLIERS = {
    "RIDE": 3.0,
    "RUN": 10.0,
    "SWIM": 25.0,
    "HIKE": 5.0,
    "WALK": 2.0,
    "WORKOUT": 4.0,
    "ROWING": 8.0,
    "CROSSFIT": 5.0,
    "SKATEBOARD": 5.0,
}


def calculate_xp(sport_type: str, distance_m: float, elevation_m: float, moving_time_s: int) -> float:
    distance_km = distance_m / 1000.0
    moving_time_min = moving_time_s / 60.0
    multiplier = SPORT_XP_MULTIPLIERS.get(str(sport_type).upper(), 2.0)
    xp = (distance_km * multiplier) + (elevation_m * 0.1) + (moving_time_min * 0.5)
    return round(xp, 2)







def _auth_for(api_key: str) -> httpx.BasicAuth:
    """Intervals.icu авторизуется BasicAuth: username=API_KEY, password=сам_ключ."""
    return httpx.BasicAuth(username="API_KEY", password=api_key)


# ═══════════════════════════════════════════════════════════════
# Per-user функции (основные)
# ═══════════════════════════════════════════════════════════════

def _month_ranges(oldest: date, newest: date) -> list[tuple[date, date]]:
    ranges = []
    cursor = oldest.replace(day=1)
    while cursor <= newest:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        ranges.append((max(oldest, cursor), min(newest, next_month - timedelta(days=1))))
        cursor = next_month
    return ranges


def _split_range(oldest: date, newest: date, days: int) -> list[tuple[date, date]]:
    ranges, cursor = [], oldest
    while cursor <= newest:
        end = min(newest, cursor + timedelta(days=days - 1))
        ranges.append((cursor, end))
        cursor = end + timedelta(days=1)
    return ranges


async def _request_json(client: httpx.AsyncClient, url: str, api_key: str, params: dict, timeout: float):
    headers = {"Accept": "application/json", "User-Agent": "FantasyLeagueApp/2.0"}
    for attempt in range(4):
        try:
            response = await client.get(url, auth=_auth_for(api_key), headers=headers, params=params, timeout=timeout)
        except httpx.RequestError:
            if attempt == 3:
                raise
            await asyncio.sleep(2 ** attempt)
            continue
        if response.status_code == 401:
            raise PermissionError("Неверный API-ключ Intervals.icu — привяжи заново в профиле")
        if response.status_code == 404:
            raise ValueError("Athlete ID не найден в Intervals.icu")
        if response.status_code == 429 or 500 <= response.status_code <= 599:
            if attempt == 3:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            try:
                delay = min(10.0, max(0.0, float(retry_after))) if retry_after else 2 ** attempt
            except ValueError:
                delay = 2 ** attempt
            await asyncio.sleep(delay)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("Intervals.icu request failed after retries")


def _records(data) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return [item for item in data["data"] if isinstance(item, dict)]
    return []


async def _fetch_activity_chunk(client, url, api_key, start: date, end: date) -> list[dict]:
    data = await _request_json(client, url, api_key,
        {"oldest": start.isoformat(), "newest": end.isoformat(), "limit": 200}, 30.0)
    rows = _records(data)
    if len(rows) < 200:
        return rows
    chunks = _split_range(start, end, 7)
    if len(chunks) == 1:
        chunks = _split_range(start, end, 1)
    result = []
    for chunk_start, chunk_end in chunks:
        await asyncio.sleep(0.25)
        chunk_data = await _request_json(client, url, api_key,
            {"oldest": chunk_start.isoformat(), "newest": chunk_end.isoformat(), "limit": 200}, 30.0)
        chunk_rows = _records(chunk_data)
        if len(chunk_rows) >= 200 and chunk_start < chunk_end:
            for day_start, day_end in _split_range(chunk_start, chunk_end, 1):
                await asyncio.sleep(0.25)
                day_data = await _request_json(client, url, api_key,
                    {"oldest": day_start.isoformat(), "newest": day_end.isoformat(), "limit": 200}, 30.0)
                result.extend(_records(day_data))
        else:
            result.extend(chunk_rows)
    return result


ProgressCallback = Callable[[str, int, int, date], Awaitable[None]]


async def _report_progress(
    callback: ProgressCallback | None,
    phase: str,
    done: int,
    total: int,
    current_month: date,
) -> None:
    if callback is not None:
        await callback(phase, done, total, current_month)


async def fetch_activities_for_user(
    api_key: str, athlete_id: str, oldest: Optional[str] = None,
    newest: Optional[str] = None, limit: int = 200,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    start = date.fromisoformat(oldest) if oldest else date.today() - timedelta(days=90)
    end = date.fromisoformat(newest) if newest else date.today()
    if start > end:
        return []
    url, result = f"{settings.INTERVALS_API_URL}/athlete/{athlete_id}/activities", []
    chunks = _month_ranges(start, end)
    async with httpx.AsyncClient() as client:
        for index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            if result:
                await asyncio.sleep(0.25)
            result.extend(await _fetch_activity_chunk(client, url, api_key, chunk_start, chunk_end))
            await _report_progress(progress_callback, "activities", index, len(chunks), chunk_start)
    return result


async def fetch_wellness_for_user(
    api_key: str, athlete_id: str, oldest: Optional[str] = None,
    newest: Optional[str] = None,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    start = date.fromisoformat(oldest) if oldest else date.today() - timedelta(days=30)
    end = date.fromisoformat(newest) if newest else date.today()
    if start > end:
        return []
    url, result = f"{settings.INTERVALS_API_URL}/athlete/{athlete_id}/wellness", []
    chunks = _month_ranges(start, end)
    async with httpx.AsyncClient() as client:
        for index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            if result:
                await asyncio.sleep(0.25)
            data = await _request_json(client, url, api_key,
                {"oldest": chunk_start.isoformat(), "newest": chunk_end.isoformat()}, 20.0)
            result.extend(_records(data))
            await _report_progress(progress_callback, "wellness", index, len(chunks), chunk_start)
    return result


async def validate_credentials(api_key: str, athlete_id: str) -> dict | None:
    """
    Проверяет валидность связки ключ + athlete_id.
    Возвращает данные атлета или None.
    Используется при подключении ключа в профиле.
    """
    url = f"{settings.INTERVALS_API_URL}/athlete/{athlete_id}"
    headers = {"Accept": "application/json", "User-Agent": "FantasyLeagueApp/2.0"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                url, auth=_auth_for(api_key), headers=headers, timeout=15.0
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.warning("Intervals credential validation failed (%s)", type(e).__name__)
            return None


