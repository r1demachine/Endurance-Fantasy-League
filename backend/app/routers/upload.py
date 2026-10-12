"""Secure upload and parsing for user-provided FIT, GPX and TCX activities.

Files are parsed in memory only. A signed, short-lived preview token contains calculated metadata,
not the uploaded file.
"""
import asyncio
import base64
import hashlib
import hmac
import io
import json
import secrets
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from statistics import mean
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import decode_access_token_claims
from ..config import get_settings
from ..database import get_db
from ..dependencies import get_current_user
from ..models import Activity, User
from ..rate_limit import get_client_address, limiter

router = APIRouter(tags=["Activity uploads"])

MAX_FILE_BYTES = 5 * 1024 * 1024
PARSE_TIMEOUT_SECONDS = 12
PREVIEW_TTL_SECONDS = 15 * 60
UPLOAD_SOURCE = "UPLOAD_SITE"
ALLOWED_EXTENSIONS = {".fit", ".gpx", ".tcx"}
FALLBACK_LTHR = 153.0  # 85% от условного HRmax 180; только для грубой оценки.
HARD_ZONE_MIN_SECONDS = 300


class UnsupportedActivityFile(ValueError):
    """The filename extension and actual file format do not match."""


class InvalidActivityFile(ValueError):
    """The uploaded file has the right extension but is invalid or incomplete."""


class HeartRateSettingsUpdate(BaseModel):
    lthr: int | None = Field(default=None, ge=80, le=220)
    max_hr: int | None = Field(default=None, ge=100, le=240)


class ConfirmUploadInput(BaseModel):
    preview_token: str = Field(..., min_length=32, max_length=8192)


def _upload_rate_key(request: Request) -> str:
    """Rate-limit by authenticated user ID, not a shared proxy IP."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        claims = decode_access_token_claims(token.strip())
        if claims:
            return f"activity-upload-user:{claims[0]}"
    return f"activity-upload-ip:{get_client_address(request)}"


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError, OverflowError):
        return None


def _local_name(tag: str) -> str:
    return str(tag).split("}")[-1].split(":")[-1]


def _tag_text(node: ET.Element, wanted: str) -> str | None:
    for item in node.iter():
        if _local_name(item.tag) == wanted and item.text:
            return item.text.strip()
    return None


def _direct_child_text(node: ET.Element, wanted: str) -> str | None:
    for item in list(node):
        if _local_name(item.tag) == wanted and item.text:
            return item.text.strip()
    return None


def _normalise_sport(value: Any) -> str:
    raw = str(value or "").lower()
    if any(part in raw for part in ("cycling", "biking", "ride", "bicycle", "virtualride")):
        return "RIDE"
    if "run" in raw:
        return "RUN"
    if "swim" in raw:
        return "SWIM"
    if "walk" in raw or "hike" in raw:
        return "WALK"
    return "WORKOUT"


def _sport_if(sport_type: str) -> float:
    return {"RIDE": 0.75, "RUN": 0.80, "SWIM": 0.75, "WALK": 0.45}.get(sport_type, 0.70)


def _distance_between(a: dict, b: dict) -> float:
    if a.get("lat") is None or a.get("lon") is None or b.get("lat") is None or b.get("lon") is None:
        return 0.0
    lat1, lat2 = radians(float(a["lat"])), radians(float(b["lat"]))
    dlat = lat2 - lat1
    dlon = radians(float(b["lon"]) - float(a["lon"]))
    term = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000.0 * 2 * asin(min(1.0, sqrt(max(0.0, term))))


def _track_distance(samples: list[dict]) -> float:
    return sum(_distance_between(a, b) for a, b in zip(samples, samples[1:]))


def _elevation_gain(samples: list[dict]) -> float:
    values = [float(s["ele"]) for s in samples if s.get("ele") is not None]
    return sum(max(0.0, b - a) for a, b in zip(values, values[1:]))


def _heart_rate_from_extensions(extensions: list[Any]) -> float | None:
    for extension in extensions or []:
        for node in extension.iter():
            if _local_name(node.tag).lower() == "hr" and node.text:
                value = _number(node.text)
                if value and 25 <= value <= 240:
                    return value
    return None


def _finalise_file_metrics(
    *,
    start: datetime | None,
    moving_time: float | None,
    elapsed_time: float | None,
    distance: float | None,
    elevation_gain: float | None,
    average_hr: float | None,
    maximum_hr: float | None,
    sport_type: str,
    samples: list[dict],
    lthr: int | None,
    user_max_hr: int | None,
) -> dict:
    times = [_parse_iso_datetime(s.get("time")) for s in samples]
    times = [t for t in times if t is not None]
    if start is None and times:
        start = min(times)
    start_utc = _utc_naive(start)
    if start_utc is None:
        raise InvalidActivityFile("В файле не найдено время начала тренировки.")

    measured_elapsed = max(0.0, (max(times) - min(times)).total_seconds()) if len(times) >= 2 else None
    moving = _number(moving_time) or measured_elapsed
    elapsed = _number(elapsed_time) or measured_elapsed or moving
    if not moving or moving <= 0:
        raise InvalidActivityFile("Не удалось определить длительность тренировки.")
    if moving > 7 * 24 * 3600:
        raise InvalidActivityFile("Длительность тренировки выглядит некорректной.")

    distance_m = _number(distance) or _track_distance(samples)
    elevation_m = _number(elevation_gain)
    if elevation_m is None or elevation_m < 0:
        elevation_m = _elevation_gain(samples)
    distance_m = max(0.0, float(distance_m or 0.0))
    elevation_m = max(0.0, float(elevation_m or 0.0))

    valid_hrs = [
        float(s["hr"]) for s in samples
        if s.get("hr") is not None and 25 <= float(s["hr"]) <= 240
    ]
    avg_hr = _number(average_hr)
    if avg_hr is None and valid_hrs:
        avg_hr = mean(valid_hrs)
    if avg_hr is not None and not 25 <= avg_hr <= 240:
        avg_hr = None
    sample_max_hr = max(valid_hrs) if valid_hrs else None
    max_hr = _number(maximum_hr)
    if max_hr is None:
        max_hr = sample_max_hr
    if max_hr is not None and not 25 <= max_hr <= 240:
        max_hr = sample_max_hr

    if lthr:
        hr_threshold = float(lthr)
        load_method = "lthr"
    elif user_max_hr:
        hr_threshold = float(user_max_hr) * 0.85
        load_method = "max_hr_estimate"
    elif avg_hr is not None:
        hr_threshold = FALLBACK_LTHR
        load_method = "duration_hr_estimate"
    else:
        hr_threshold = None
        load_method = "duration_sport_estimate"

    intensity = min(1.5, max(0.3, avg_hr / hr_threshold)) if avg_hr and hr_threshold else _sport_if(sport_type)
    hr_tss = max(0.0, (float(moving) / 3600.0) * intensity ** 2 * 100.0)
    hard_threshold = hr_threshold * 0.95 if hr_threshold else 0.80 * 180.0

    ordered_samples = []
    for sample in samples:
        sample_time = _parse_iso_datetime(sample.get("time"))
        sample_hr = _number(sample.get("hr"))
        if sample_time is not None and sample_hr is not None and 25 <= sample_hr <= 240:
            ordered_samples.append((sample_time, sample_hr))
    ordered_samples.sort(key=lambda item: item[0])
    hard_secs = 0
    for (time_a, hr_a), (time_b, _) in zip(ordered_samples, ordered_samples[1:]):
        seconds = (time_b - time_a).total_seconds()
        # A recording gap should not be counted as hard work.
        if 0 < seconds <= 30 and hr_a >= hard_threshold:
            hard_secs += int(round(seconds))

    return {
        "name": {
            "RIDE": "Загруженная велотренировка",
            "RUN": "Загруженная беговая тренировка",
            "SWIM": "Загруженная тренировка по плаванию",
            "WALK": "Загруженная ходьба",
        }.get(sport_type, "Загруженная тренировка"),
        "sport_type": sport_type,
        "start_date": start_utc.isoformat(),
        "moving_time": int(round(moving)),
        "elapsed_time": int(round(elapsed or moving)),
        "distance": round(distance_m, 2),
        "elevation_gain": round(elevation_m, 2),
        "average_heartrate": round(avg_hr, 1) if avg_hr is not None else None,
        "max_heartrate": round(max_hr, 1) if max_hr is not None else None,
        "training_load": round(hr_tss, 2),
        "intensity": round(intensity, 4),
        "hard_secs": hard_secs,
        "load_method": load_method,
    }


def _parse_fit(data: bytes, lthr: int | None, user_max_hr: int | None) -> dict:
    from fitparse import FitFile

    try:
        fit = FitFile(io.BytesIO(data))
        sessions = [
            {field.name: field.value for field in message}
            for message in fit.get_messages("session")
        ]
        session = sessions[0] if sessions else {}
        samples = []
        for message in fit.get_messages("record"):
            record = {field.name: field.value for field in message}
            samples.append({
                "time": record.get("timestamp"),
                "hr": _number(record.get("heart_rate")),
                "ele": _number(record.get("altitude")),
                "distance": _number(record.get("distance")),
            })
        activity_start = _parse_iso_datetime(session.get("start_time"))
        if activity_start is None:
            activity_start = min(
                (t for t in (_parse_iso_datetime(s.get("time")) for s in samples) if t is not None),
                default=None,
            )
        distance = _number(session.get("total_distance"))
        if not distance:
            distance = max((_number(s.get("distance")) or 0.0 for s in samples), default=0.0)
        return _finalise_file_metrics(
            start=activity_start,
            moving_time=_number(session.get("total_timer_time")),
            elapsed_time=_number(session.get("total_elapsed_time")),
            distance=distance,
            elevation_gain=_number(session.get("total_ascent")),
            average_hr=_number(session.get("avg_heart_rate")),
            maximum_hr=_number(session.get("max_heart_rate")),
            sport_type=_normalise_sport(session.get("sport") or session.get("sub_sport")),
            samples=samples,
            lthr=lthr,
            user_max_hr=user_max_hr,
        )
    except (InvalidActivityFile, UnsupportedActivityFile):
        raise
    except Exception as exc:
        raise InvalidActivityFile("FIT-файл повреждён или не содержит тренировку.") from exc


def _parse_gpx(data: bytes, lthr: int | None, user_max_hr: int | None) -> dict:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise InvalidActivityFile("GPX с DTD/ENTITY не поддерживается.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise InvalidActivityFile("GPX-файл содержит некорректный XML.") from exc
    if _local_name(root.tag).lower() != "gpx":
        raise UnsupportedActivityFile("Расширение .gpx не соответствует содержимому файла.")
    try:
        import gpxpy
        gpx = gpxpy.parse(data.decode("utf-8-sig"))
        samples = []
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    samples.append({
                        "time": point.time, "hr": _heart_rate_from_extensions(point.extensions),
                        "ele": point.elevation, "lat": point.latitude, "lon": point.longitude,
                    })
        for route in gpx.routes:
            for point in route.points:
                samples.append({
                    "time": point.time, "hr": _heart_rate_from_extensions(point.extensions),
                    "ele": point.elevation, "lat": point.latitude, "lon": point.longitude,
                })
        return _finalise_file_metrics(
            start=None, moving_time=None, elapsed_time=None, distance=None,
            elevation_gain=None, average_hr=None, maximum_hr=None,
            sport_type="WORKOUT", samples=samples, lthr=lthr, user_max_hr=user_max_hr,
        )
    except (InvalidActivityFile, UnsupportedActivityFile):
        raise
    except Exception as exc:
        raise InvalidActivityFile("GPX-файл повреждён или не содержит трек тренировки.") from exc


def _parse_tcx(data: bytes, lthr: int | None, user_max_hr: int | None) -> dict:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise InvalidActivityFile("TCX с DTD/ENTITY не поддерживается.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise InvalidActivityFile("TCX-файл содержит некорректный XML.") from exc
    if _local_name(root.tag).lower() != "trainingcenterdatabase":
        raise UnsupportedActivityFile("Расширение .tcx не соответствует содержимому файла.")

    activity = next((node for node in root.iter() if _local_name(node.tag) == "Activity"), None)
    if activity is None:
        raise InvalidActivityFile("В TCX-файле не найдена тренировка.")
    start = _parse_iso_datetime(_direct_child_text(activity, "Id"))
    sport = _normalise_sport(activity.attrib.get("Sport"))
    laps = [node for node in activity.iter() if _local_name(node.tag) == "Lap"]
    samples = []
    lap_distances = []
    lap_times = []
    total_ascent = 0.0
    for lap in laps:
        lap_distance = _number(_direct_child_text(lap, "DistanceMeters"))
        lap_elapsed = _number(_direct_child_text(lap, "TotalTimeSeconds"))
        if lap_distance and lap_distance > 0:
            lap_distances.append(lap_distance)
        if lap_elapsed and lap_elapsed > 0:
            lap_times.append(lap_elapsed)
        lap_samples = []
        for node in lap.iter():
            if _local_name(node.tag) != "Trackpoint":
                continue
            point_time = _parse_iso_datetime(_tag_text(node, "Time"))
            lat = lon = None
            for position in node.iter():
                if _local_name(position.tag) == "Position":
                    lat = _number(_tag_text(position, "LatitudeDegrees"))
                    lon = _number(_tag_text(position, "LongitudeDegrees"))
                    break
            hr_value = None
            for heart_node in node.iter():
                if _local_name(heart_node.tag) == "HeartRateBpm":
                    hr_value = _number(_tag_text(heart_node, "Value"))
                    break
            lap_samples.append({
                "time": point_time, "hr": hr_value,
                "ele": _number(_tag_text(node, "AltitudeMeters")),
                "distance": _number(_tag_text(node, "DistanceMeters")),
                "lat": lat, "lon": lon,
            })
        samples.extend(lap_samples)
        total_ascent += _elevation_gain(lap_samples)

    fallback_distance = sum(lap_distances) if lap_distances else _track_distance(samples)
    fallback_elapsed = sum(lap_times) if lap_times else None
    return _finalise_file_metrics(
        start=start, moving_time=fallback_elapsed, elapsed_time=fallback_elapsed,
        distance=fallback_distance, elevation_gain=total_ascent,
        average_hr=None, maximum_hr=None, sport_type=sport,
        samples=samples, lthr=lthr, user_max_hr=user_max_hr,
    )


def _parse_activity_file(data: bytes, extension: str, lthr: int | None, user_max_hr: int | None) -> dict:
    extension = extension.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedActivityFile("Поддерживаются только файлы .fit, .gpx и .tcx.")
    if len(data) < 12:
        raise InvalidActivityFile("Файл слишком маленький или повреждён.")
    if extension == ".fit":
        # FIT signature is bytes 8..11. Other binary formats are never unpacked.
        if data[8:12] != b".FIT":
            raise UnsupportedActivityFile("Расширение .fit не соответствует содержимому файла.")
        return _parse_fit(data, lthr, user_max_hr)
    if extension == ".gpx":
        return _parse_gpx(data, lthr, user_max_hr)
    return _parse_tcx(data, lthr, user_max_hr)


def _encode_preview(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    key = (get_settings().JWT_SECRET + ":activity-upload-preview-v1").encode("utf-8")
    signature = hmac.new(key, encoded.encode("ascii"), hashlib.sha256).digest()
    return encoded + "." + base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")


def _decode_preview(token: str) -> dict:
    try:
        encoded, signature_text = token.split(".", 1)
        if len(encoded) > 7000:
            raise ValueError("token too long")
        key = (get_settings().JWT_SECRET + ":activity-upload-preview-v1").encode("utf-8")
        expected = hmac.new(key, encoded.encode("ascii"), hashlib.sha256).digest()
        signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        if not hmac.compare_digest(expected, signature):
            raise ValueError("bad signature")
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or int(payload.get("expires_at", 0)) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Предпросмотр истёк или недействителен. Выбери файл и загрузи его заново.") from exc


def _find_intervals_duplicate(db: Session, user_id: int, start_date: datetime, moving_time: int) -> Activity | None:
    return (
        db.query(Activity)
        .filter(
            Activity.user_id == user_id,
            Activity.source == "INTERVALS",
            Activity.start_date >= start_date - timedelta(minutes=5),
            Activity.start_date <= start_date + timedelta(minutes=5),
            Activity.moving_time >= max(1, int(moving_time * 0.90)),
            Activity.moving_time <= int(moving_time * 1.10),
        )
        .order_by(Activity.start_date.asc())
        .first()
    )


@router.get("/profile/heart-rate")
def get_heart_rate_settings(current: User = Depends(get_current_user)):
    return {"lthr": current.lthr, "max_hr": current.max_hr}


@router.patch("/profile/heart-rate")
def update_heart_rate_settings(
    data: HeartRateSettingsUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fields = data.model_fields_set
    if not fields:
        raise HTTPException(status_code=422, detail="Укажи LTHR и/или максимальный пульс.")
    next_lthr = data.lthr if "lthr" in fields else current.lthr
    next_max_hr = data.max_hr if "max_hr" in fields else current.max_hr
    if next_lthr is not None and next_max_hr is not None and next_lthr >= next_max_hr:
        raise HTTPException(status_code=422, detail="LTHR должен быть ниже максимального пульса.")
    if "lthr" in fields:
        current.lthr = data.lthr
    if "max_hr" in fields:
        current.max_hr = data.max_hr
    db.commit()
    db.refresh(current)
    return {"lthr": current.lthr, "max_hr": current.max_hr, "saved": True}


@router.post("/upload/activity")
@limiter.limit("10/hour", key_func=_upload_rate_key)
async def upload_activity_preview(
    request: Request,
    file: UploadFile = File(...),
    current: User = Depends(get_current_user),
):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        await file.close()
        raise HTTPException(status_code=415, detail="Поддерживаются только .fit, .gpx и .tcx.")
    try:
        content = await file.read(MAX_FILE_BYTES + 1)
    finally:
        await file.close()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой.")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Размер файла превышает 5 МБ.")

    try:
        parsed = await asyncio.wait_for(
            asyncio.to_thread(_parse_activity_file, content, extension, current.lthr, current.max_hr),
            timeout=PARSE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=408, detail="Разбор файла занял слишком много времени. Попробуй экспортировать файл заново.") from exc
    except UnsupportedActivityFile as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except InvalidActivityFile as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Не удалось прочитать тренировку из файла.") from exc

    token_payload = {
        "user_id": current.id,
        "nonce": secrets.token_hex(16),
        "expires_at": int(datetime.now(timezone.utc).timestamp()) + PREVIEW_TTL_SECONDS,
        **parsed,
    }
    return {"preview_token": _encode_preview(token_payload), "preview": parsed}


@router.post("/upload/activity/confirm")
def confirm_activity_upload(
    data: ConfirmUploadInput = Body(...),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    preview = _decode_preview(data.preview_token)
    if preview.get("user_id") != current.id:
        raise HTTPException(status_code=403, detail="Этот предпросмотр создан другим пользователем.")
    required = ("nonce", "start_date", "moving_time", "elapsed_time", "sport_type", "training_load", "intensity")
    if any(key not in preview for key in required):
        raise HTTPException(status_code=422, detail="Предпросмотр неполный. Загрузи файл заново.")

    activity_id = f"UPLOAD_SITE:{preview['nonce']}"
    if db.query(Activity).filter(
        Activity.user_id == current.id,
        Activity.intervals_activity_id == activity_id,
    ).first():
        raise HTTPException(status_code=409, detail="Эта тренировка уже была сохранена.")

    try:
        start_date = datetime.fromisoformat(str(preview["start_date"]))
        moving_time = int(preview["moving_time"])
        elapsed_time = int(preview.get("elapsed_time") or moving_time)
        distance = max(0.0, float(preview.get("distance") or 0.0))
        elevation = max(0.0, float(preview.get("elevation_gain") or 0.0))
        training_load = max(0.0, float(preview["training_load"]))
        intensity = min(1.5, max(0.3, float(preview["intensity"])))
        hard_secs = max(0, int(preview.get("hard_secs") or 0))
        average_hr = preview.get("average_heartrate")
        maximum_hr = preview.get("max_heartrate")
    except (TypeError, ValueError, OverflowError) as exc:
        raise HTTPException(status_code=422, detail="Данные предпросмотра повреждены. Загрузи файл заново.") from exc
    if moving_time <= 0 or moving_time > 7 * 24 * 3600:
        raise HTTPException(status_code=422, detail="Некорректная длительность тренировки.")

    duplicate = _find_intervals_duplicate(db, current.id, start_date, moving_time)
    if duplicate:
        when = duplicate.start_date.strftime("%d.%m.%Y %H:%M") if duplicate.start_date else "время неизвестно"
        mins = round((duplicate.moving_time or 0) / 60)
        raise HTTPException(
            status_code=409,
            detail=f"Похожа тренировка из Intervals.icu уже есть: «{duplicate.name or 'Без названия'}», {when}, длительность {mins} мин.",
        )

    from ..services.xp import round_xp
    from .sync import _recalculate_user_xp, _recalculate_user_xp_v6

    before_xp = float(current.total_xp or 0)
    activity = Activity(
        user_id=current.id,
        intervals_activity_id=activity_id,
        source=UPLOAD_SOURCE,
        name=str(preview.get("name") or "Загруженная тренировка")[:255],
        sport_type=str(preview.get("sport_type") or "WORKOUT")[:32],
        distance=distance,
        moving_time=moving_time,
        elapsed_time=elapsed_time,
        elevation_gain=elevation,
        average_speed=(distance / moving_time) if distance and moving_time else None,
        average_heartrate=float(average_hr) if average_hr is not None else None,
        max_heartrate=float(maximum_hr) if maximum_hr is not None else None,
        training_load=training_load,
        intensity=intensity,
        hard_secs=hard_secs,
        is_manual=False,
        start_date=start_date,
        start_date_local=start_date,
        indoor=False,
        is_indoor=False,
    )
    db.add(activity)
    try:
        db.flush()
        if get_settings().XP_ENGINE == "v6":
            _recalculate_user_xp_v6(db, current)
        else:
            _recalculate_user_xp(db, current)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(activity)
    db.refresh(current)
    return {
        "message": "Тренировка загружена, XP пересчитан.",
        "activity": {
            "id": activity.id,
            "name": activity.name,
            "source": activity.source,
            "start_date": activity.start_date.isoformat() if activity.start_date else None,
            "moving_time": activity.moving_time,
            "distance": activity.distance,
            "elevation_gain": activity.elevation_gain,
            "average_heartrate": activity.average_heartrate,
            "training_load": activity.training_load,
            "hard_secs": activity.hard_secs,
            "xp_earned": round_xp(activity.xp_earned or 0),
        },
        "new_xp": round_xp(float(current.total_xp or 0) - before_xp),
        "total_xp": round_xp(current.total_xp or 0),
        "level": current.level,
    }
