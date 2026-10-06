"""Intervals.icu API client — только per-user (ключ берётся из аккаунта пользователя)."""

import httpx
from datetime import datetime, timedelta
from typing import Optional
from ..config import get_settings

settings = get_settings()

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

async def fetch_activities_for_user(
    api_key: str,
    athlete_id: str,
    oldest: Optional[str] = None,
    newest: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Тянет активности конкретного юзера его ключом (JSON API)."""
    if not oldest:
        oldest = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    if not newest:
        newest = datetime.now().strftime("%Y-%m-%d")

    url = f"{settings.INTERVALS_API_URL}/athlete/{athlete_id}/activities"
    params = {"oldest": oldest, "newest": newest, "limit": limit}
    headers = {"Accept": "application/json", "User-Agent": "FantasyLeagueApp/2.0"}

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url, auth=_auth_for(api_key), headers=headers, params=params, timeout=30.0
        )

        if response.status_code == 401:
            raise PermissionError("Неверный API-ключ Intervals.icu — привяжи заново в профиле")
        if response.status_code == 404:
            raise ValueError(f"Athlete ID '{athlete_id}' не найден в Intervals.icu")
        if response.status_code >= 400:
            print(f"❌ ОШИБКА API activities: {response.status_code}")
            print(f"📄 {response.text[:500]}")
            return []

        data = response.json()
        if isinstance(data, list):
            activities = data
        elif isinstance(data, dict) and "data" in data:
            activities = data["data"]
        else:
            activities = []

        print(f"✅ [{athlete_id}] Получено {len(activities)} активностей ({oldest} → {newest})")
        return activities


async def fetch_wellness_for_user(
    api_key: str,
    athlete_id: str,
    oldest: Optional[str] = None,
    newest: Optional[str] = None,
) -> list[dict]:
    """Сон, HRV, resting HR для конкретного юзера."""
    if not oldest:
        oldest = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not newest:
        newest = datetime.now().strftime("%Y-%m-%d")

    url = f"{settings.INTERVALS_API_URL}/athlete/{athlete_id}/wellness"
    params = {"oldest": oldest, "newest": newest}
    headers = {"Accept": "application/json", "User-Agent": "FantasyLeagueApp/2.0"}

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url, auth=_auth_for(api_key), headers=headers, params=params, timeout=20.0
        )
        if response.status_code >= 400:
            print(f"⚠️ Wellness for {athlete_id}: HTTP {response.status_code}")
            return []
        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return []


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
            print(f"⚠️ validate_credentials error: {e}")
            return None


