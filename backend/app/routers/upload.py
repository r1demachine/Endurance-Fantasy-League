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
import multiprocessing
import re
import secrets
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException
from datetime import datetime, timedelta, timezone
from math import asin, ceil, cos, exp, floor, radians, sin, sqrt
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from starlette.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import decode_access_token_claims
from ..config import get_settings
from ..database import get_db
from ..dependencies import get_current_user, require_privacy_consent
from ..models import Activity, HeartRateSettingsHistory, User
from ..rate_limit import get_client_address, limiter

router = APIRouter(prefix="/api", tags=["Activity uploads"])

MAX_FILE_BYTES = 5 * 1024 * 1024
PARSE_TIMEOUT_SECONDS = 12
PREVIEW_TTL_SECONDS = 15 * 60
UPLOAD_SOURCE = "UPLOAD_SITE"
ALLOWED_EXTENSIONS = {".fit", ".gpx", ".tcx"}
FALLBACK_LTHR = 153.0  # 85% от условного HRmax 180; только для грубой оценки.
HARD_ZONE_MIN_SECONDS = 300
MAX_ACTIVITY_SAMPLES = 25000
MAX_PARALLEL_PARSERS = 2
_PARSE_SEMAPHORE = asyncio.Semaphore(MAX_PARALLEL_PARSERS)


class UnsupportedActivityFile(ValueError):
    """The filename extension and actual file format do not match."""


class InvalidActivityFile(ValueError):
    """The uploaded file has the right extension but is invalid or incomplete."""


class HeartRateSettingsUpdate(BaseModel):
    lthr: int | None = Field(default=None, ge=80, le=220)
    max_hr: int | None = Field(default=None, ge=100, le=240)
    resting_hr: int | None = Field(default=None, ge=30, le=100)
    timezone_name: str | None = Field(default=None, min_length=1, max_length=64)


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


def _user_zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise InvalidActivityFile("Неизвестный часовой пояс пользователя.") from exc


def _local_to_utc_naive(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(zone).replace(tzinfo=None)
    return value.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)


def _sample_time_utc_naive(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _decode_xml_utf8(data: bytes) -> str:
    try:
        content = data.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise InvalidActivityFile("GPX/TCX должны быть закодированы в UTF-8.") from exc
    declaration = re.match(r"""\s*<\?xml\s+[^?]*encoding\s*=\s*['"]([^'"]+)['"][^?]*\?>""", content, re.IGNORECASE)
    if declaration and declaration.group(1).lower().replace("_", "-") not in {"utf-8", "utf8"}:
        raise InvalidActivityFile("Поддерживается только кодировка UTF-8.")
    return content


def _secure_xml_root(content: str):
    try:
        return ET.fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ET.ParseError, DefusedXmlException, ValueError) as exc:
        raise InvalidActivityFile("XML-файл некорректен или содержит запрещённые DTD/ENTITY.") from exc


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
    resting_hr: int | None = None,
    start_local: datetime | None = None,
    user_timezone: str | None = "UTC",
) -> dict:
    zone = _user_zone(user_timezone)
    raw_times = [_parse_iso_datetime(sample.get("time")) for sample in samples]
    raw_times = [value for value in raw_times if value is not None]
    if start is None and raw_times:
        start = min(raw_times, key=lambda value: _sample_time_utc_naive(value, zone))
    if start is None:
        raise InvalidActivityFile("В файле не найдено время начала тренировки.")

    if start_local is not None:
        start_date_local = start_local.replace(tzinfo=None)
        start_utc = _utc_naive(start) if start.tzinfo is not None else _local_to_utc_naive(start_date_local, zone)
    elif start.tzinfo is None:
        start_date_local = start
        start_utc = _local_to_utc_naive(start, zone)
    else:
        start_utc = _utc_naive(start)
        start_date_local = start.astimezone(zone).replace(tzinfo=None) if start.utcoffset() == timedelta(0) else start.replace(tzinfo=None)

    if start_utc is None:
        raise InvalidActivityFile("В файле не найдено время начала тренировки.")
    times = [_sample_time_utc_naive(value, zone) for value in raw_times]
    measured_elapsed = max(0.0, (max(times) - min(times)).total_seconds()) if len(times) >= 2 else None
    moving = _number(moving_time) or measured_elapsed
    elapsed = _number(elapsed_time) or measured_elapsed or moving
    if not moving or moving <= 0:
        raise InvalidActivityFile("Не удалось определить длительность тренировки.")
    if moving > 7 * 24 * 3600:
        raise InvalidActivityFile("Длительность тренировки выглядит некорректной.")
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if start_utc > now_utc:
        raise InvalidActivityFile("Начало тренировки находится в будущем.")
    if start_utc < now_utc - timedelta(days=30):
        raise InvalidActivityFile("Можно загружать тренировки не старше 30 дней.")
    if measured_elapsed is None or measured_elapsed <= 0:
        raise InvalidActivityFile("Недостаточно временных точек трека для проверки длительности.")
    if float(moving) > measured_elapsed * 1.2:
        raise InvalidActivityFile("Длительность превышает охват временных меток более чем на 20%.")

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

    # HRSS: normalized Banister TRIMP, the heart-rate load model used by Intervals.icu.
    # One hour at LTHR is normalized to approximately 100 load points.
    # After normalization the sex-specific coefficient cancels out; this uses
    # the common 1.92 exponent. Without athlete-specific settings the result
    # is explicitly marked as an estimate.
    ordered_samples = []
    for sample in samples:
        sample_time = _parse_iso_datetime(sample.get("time"))
        sample_hr = _number(sample.get("hr"))
        if sample_time is not None and sample_hr is not None and 25 <= sample_hr <= 240:
            ordered_samples.append((_sample_time_utc_naive(sample_time, zone), sample_hr))
    ordered_samples.sort(key=lambda item: item[0])

    observed_max_hr = max(valid_hrs) if valid_hrs else max_hr
    if user_max_hr is not None:
        # If this activity exceeds the stored maximum, use the observed peak
        # for its own load calculation while separately offering calibration.
        formula_max_hr = float(max(user_max_hr, observed_max_hr or user_max_hr))
    else:
        # Fallback only until the athlete supplies a measured maximum HR.
        formula_max_hr = float(max(190, observed_max_hr or 0))
    formula_resting_hr = float(resting_hr if resting_hr is not None else 50)
    formula_resting_hr = min(formula_resting_hr, formula_max_hr - 2)

    if lthr is not None and formula_resting_hr < lthr < formula_max_hr:
        hr_threshold = float(lthr)
    else:
        # Do not treat average HR as threshold. Estimate LTHR conservatively
        # from max HR only when no usable user-specific threshold exists.
        hr_threshold = formula_max_hr * 0.95
    hr_threshold = min(formula_max_hr - 1, max(formula_resting_hr + 1, hr_threshold))

    threshold_reserve = (hr_threshold - formula_resting_hr) / (formula_max_hr - formula_resting_hr)
    threshold_weight = threshold_reserve * exp(1.92 * threshold_reserve)
    hr_stress_seconds = 0.0
    covered_seconds = 0.0

    def _hr_weight(heart_rate: float) -> float:
        # Clip HR to the physiological range just as the HRSS model does.
        clipped_hr = min(formula_max_hr, max(formula_resting_hr, heart_rate))
        reserve = (clipped_hr - formula_resting_hr) / (formula_max_hr - formula_resting_hr)
        return reserve * exp(1.92 * reserve)

    for (time_a, hr_a), (time_b, _) in zip(ordered_samples, ordered_samples[1:]):
        seconds = (time_b - time_a).total_seconds()
        # Never count large recording gaps as sustained effort.
        if 0 < seconds <= 30:
            hr_stress_seconds += _hr_weight(hr_a) * seconds
            covered_seconds += seconds

    if covered_seconds < float(moving) * 0.5:
        raise InvalidActivityFile("Для загрузки нужен реальный поток пульса с покрытием не менее 50% длительности.")
    if threshold_weight > 0:
        hr_tss = (hr_stress_seconds / (threshold_weight * 3600.0)) * 100.0
        if resting_hr is None:
            load_method = "hrss_estimated_resting"
        elif lthr is None or not (formula_resting_hr < lthr < formula_max_hr):
            load_method = "hrss_estimated_threshold"
        elif user_max_hr is None:
            load_method = "hrss_estimated_max"
        else:
            load_method = "hrss"
    else:
        raise InvalidActivityFile("Нет достаточного потока пульса для надёжного расчёта нагрузки.")

    hr_tss = max(0.0, hr_tss)
    intensity = min(1.5, max(0.3, sqrt(hr_tss / max(float(moving) / 3600.0 * 100.0, 1e-9))))
    hard_threshold = hr_threshold * 0.95

    hard_secs = 0
    for (time_a, hr_a), (time_b, _) in zip(ordered_samples, ordered_samples[1:]):
        seconds = (time_b - time_a).total_seconds()
        if 0 < seconds <= 30 and hr_a >= hard_threshold:
            hard_secs += int(round(seconds))

    # Conservative, one-way auto-calibration: never lower user settings.
    auto_zone_updates: dict[str, int] = {}
    observed_max_hr = max(valid_hrs) if valid_hrs else max_hr
    next_max_hr = user_max_hr
    if user_max_hr is not None and observed_max_hr is not None and observed_max_hr > user_max_hr:
        next_max_hr = min(240, int(round(observed_max_hr)))
        if next_max_hr > user_max_hr:
            auto_zone_updates["max_hr"] = next_max_hr

    # Raise LTHR only if the recording contains a continuous hour above the
    # configured threshold. Any low sample or gap >30 s resets the segment.
    if lthr is not None and ordered_samples:
        segments: list[list[tuple[datetime, float]]] = []
        current_segment: list[tuple[datetime, float]] = []
        for sample in ordered_samples:
            sample_time, sample_hr = sample
            if sample_hr <= lthr:
                if current_segment:
                    segments.append(current_segment)
                    current_segment = []
                continue
            if current_segment and (sample_time - current_segment[-1][0]).total_seconds() > 30:
                segments.append(current_segment)
                current_segment = []
            current_segment.append(sample)
        if current_segment:
            segments.append(current_segment)

        for segment in segments:
            if len(segment) < 2 or (segment[-1][0] - segment[0][0]).total_seconds() < 3600:
                continue
            hour_end = segment[0][0] + timedelta(seconds=3600)
            hour_hrs = [hr for sample_time, hr in segment if sample_time <= hour_end]
            if len(hour_hrs) >= 2:
                candidate_lthr = int(round(mean(hour_hrs)))
                effective_max = next_max_hr or user_max_hr
                if effective_max is not None:
                    min_allowed = int(ceil(0.75 * effective_max))
                    max_allowed = int(floor(0.97 * effective_max))
                    candidate_lthr = min(max_allowed, max(min_allowed, candidate_lthr))
                if candidate_lthr > lthr and (effective_max is None or candidate_lthr < effective_max):
                    auto_zone_updates["lthr"] = candidate_lthr
                    break

    return {
        "name": {
            "RIDE": "Загруженная велотренировка",
            "RUN": "Загруженная беговая тренировка",
            "SWIM": "Загруженная тренировка по плаванию",
            "WALK": "Загруженная ходьба",
        }.get(sport_type, "Загруженная тренировка"),
        "sport_type": sport_type,
        "start_date": start_utc.isoformat(),
        "start_date_local": start_date_local.isoformat(),
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
        "auto_zone_updates": auto_zone_updates,
    }


def _parse_fit(data: bytes, lthr: int | None, user_max_hr: int | None, resting_hr: int | None = None, user_timezone: str | None = "UTC") -> dict:
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
            if len(samples) >= MAX_ACTIVITY_SAMPLES:
                raise InvalidActivityFile("В файле слишком много точек (лимит 25 000).")
            record = {field.name: field.value for field in message}
            record_time = record.get("timestamp")
            if isinstance(record_time, datetime) and record_time.tzinfo is None:
                record_time = record_time.replace(tzinfo=timezone.utc)
            samples.append({
                "time": record_time,
                "hr": _number(record.get("heart_rate")),
                "ele": _number(record.get("altitude")),
                "distance": _number(record.get("distance")),
            })
        activity_start = _parse_iso_datetime(session.get("start_time"))
        local_start = _parse_iso_datetime(session.get("local_timestamp"))
        if activity_start is not None and activity_start.tzinfo is None:
            activity_start = activity_start.replace(tzinfo=timezone.utc)
        if activity_start is None and local_start is not None:
            # FIT local_timestamp is a wall-clock value; _finalise converts it
            # to UTC using the user's configured IANA timezone.
            activity_start = local_start
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
            start_local=local_start,
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
            resting_hr=resting_hr,
            user_timezone=user_timezone,
        )
    except (InvalidActivityFile, UnsupportedActivityFile):
        raise
    except Exception as exc:
        raise InvalidActivityFile("FIT-файл повреждён или не содержит тренировку.") from exc


def _parse_gpx(data: bytes, lthr: int | None, user_max_hr: int | None, resting_hr: int | None = None, user_timezone: str | None = "UTC") -> dict:
    xml_text = _decode_xml_utf8(data)
    root = _secure_xml_root(xml_text)
    if _local_name(root.tag).lower() != "gpx":
        raise UnsupportedActivityFile("Расширение .gpx не соответствует содержимому файла.")
    try:
        point_count = sum(1 for node in root.iter() if _local_name(node.tag).lower() in {"trkpt", "rtept"})
        if point_count > MAX_ACTIVITY_SAMPLES:
            raise InvalidActivityFile("В файле слишком много точек (лимит 25 000).")
        import gpxpy
        gpx = gpxpy.parse(xml_text)
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
            start=None, start_local=None, user_timezone=user_timezone,
            moving_time=None, elapsed_time=None, distance=None,
            elevation_gain=None, average_hr=None, maximum_hr=None,
            sport_type="WORKOUT", samples=samples, lthr=lthr, user_max_hr=user_max_hr,
            resting_hr=resting_hr,
        )
    except (InvalidActivityFile, UnsupportedActivityFile):
        raise
    except Exception as exc:
        raise InvalidActivityFile("GPX-файл повреждён или не содержит трек тренировки.") from exc


def _parse_tcx(data: bytes, lthr: int | None, user_max_hr: int | None, resting_hr: int | None = None, user_timezone: str | None = "UTC") -> dict:
    xml_text = _decode_xml_utf8(data)
    root = _secure_xml_root(xml_text)
    if _local_name(root.tag).lower() != "trainingcenterdatabase":
        raise UnsupportedActivityFile("Расширение .tcx не соответствует содержимому файла.")

    activity = next((node for node in root.iter() if _local_name(node.tag) == "Activity"), None)
    if activity is None:
        raise InvalidActivityFile("В TCX-файле не найдена тренировка.")
    start = _parse_iso_datetime(_direct_child_text(activity, "Id"))
    sport = _normalise_sport(activity.attrib.get("Sport"))
    laps = [node for node in activity.iter() if _local_name(node.tag) == "Lap"]
    point_count = sum(1 for node in root.iter() if _local_name(node.tag) == "Trackpoint")
    if point_count > MAX_ACTIVITY_SAMPLES:
        raise InvalidActivityFile("В файле слишком много точек (лимит 25 000).")
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
        if len(samples) + len(lap_samples) > MAX_ACTIVITY_SAMPLES:
            raise InvalidActivityFile("В файле слишком много точек (лимит 25 000).")
        samples.extend(lap_samples)
        total_ascent += _elevation_gain(lap_samples)

    fallback_distance = sum(lap_distances) if lap_distances else _track_distance(samples)
    fallback_elapsed = sum(lap_times) if lap_times else None
    return _finalise_file_metrics(
        start=start, start_local=None,
        moving_time=fallback_elapsed, elapsed_time=fallback_elapsed,
        distance=fallback_distance, elevation_gain=total_ascent,
        average_hr=None, maximum_hr=None, sport_type=sport,
        samples=samples, lthr=lthr, user_max_hr=user_max_hr, resting_hr=resting_hr,
        user_timezone=user_timezone,
    )


def _parse_activity_file(
    data: bytes,
    extension: str,
    lthr: int | None,
    user_max_hr: int | None,
    resting_hr: int | None = None,
    user_timezone: str | None = "UTC",
) -> dict:
    extension = extension.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedActivityFile("Поддерживаются только файлы .fit, .gpx и .tcx.")
    if len(data) < 12:
        raise InvalidActivityFile("Файл слишком маленький или повреждён.")
    if extension == ".fit":
        if data[8:12] != b".FIT":
            raise UnsupportedActivityFile("Расширение .fit не соответствует содержимому файла.")
        return _parse_fit(data, lthr, user_max_hr, resting_hr, user_timezone)
    if extension == ".gpx":
        return _parse_gpx(data, lthr, user_max_hr, resting_hr, user_timezone)
    return _parse_tcx(data, lthr, user_max_hr, resting_hr, user_timezone)


def _activity_parser_process(send_conn, data, extension, lthr, max_hr, resting_hr, user_timezone):
    """Child process lets the parent kill a parser that exceeds its deadline."""
    try:
        send_conn.send(("ok", _parse_activity_file(data, extension, lthr, max_hr, resting_hr, user_timezone)))
    except UnsupportedActivityFile as exc:
        send_conn.send(("unsupported", str(exc)))
    except InvalidActivityFile as exc:
        send_conn.send(("invalid", str(exc)))
    except BaseException:
        try:
            send_conn.send(("invalid", "Не удалось прочитать файл тренировки."))
        except Exception:
            pass
    finally:
        send_conn.close()


def _parse_activity_file_hard_timeout(data, extension, lthr, max_hr, resting_hr, user_timezone):
    context = multiprocessing.get_context("spawn")
    recv_conn, send_conn = context.Pipe(duplex=False)
    process = context.Process(
        target=_activity_parser_process,
        args=(send_conn, data, extension, lthr, max_hr, resting_hr, user_timezone),
        daemon=True,
    )
    try:
        process.start()
        send_conn.close()
        process.join(PARSE_TIMEOUT_SECONDS)
        if process.is_alive():
            process.terminate()
            process.join(1)
            if process.is_alive():
                process.kill()
                process.join(1)
            raise TimeoutError("Разбор файла занял слишком много времени.")
        if not recv_conn.poll(0.2):
            raise InvalidActivityFile("Парсер завершился без результата.")
        status, payload = recv_conn.recv()
        if status == "unsupported":
            raise UnsupportedActivityFile(payload)
        if status == "invalid":
            raise InvalidActivityFile(payload)
        if status != "ok" or not isinstance(payload, dict):
            raise InvalidActivityFile("Результат парсера повреждён.")
        return payload
    finally:
        recv_conn.close()
        try:
            send_conn.close()
        except Exception:
            pass
        if process.is_alive():
            process.terminate()
            process.join(1)
        process.close()


async def _parse_activity_file_bounded(data, extension, lthr, max_hr, resting_hr, user_timezone):
    async with _PARSE_SEMAPHORE:
        return await asyncio.to_thread(
            _parse_activity_file_hard_timeout,
            data, extension, lthr, max_hr, resting_hr, user_timezone,
        )


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


def _find_intervals_duplicate(
    db: Session,
    user_id: int,
    start_date: datetime,
    moving_time: int,
    start_date_local: datetime | None = None,
    sources: tuple[str, ...] = ("INTERVALS", "UPLOAD_SITE", "UPLOAD_TELEGRAM"),
) -> Activity | None:
    from ..services.activity_dedupe import find_matching_activity
    return find_matching_activity(
        db, user_id, start_date, start_date_local, moving_time, sources=sources,
    )


@router.get("/profile/heart-rate")
def get_heart_rate_settings(current: User = Depends(get_current_user)):
    return {
        "lthr": current.lthr,
        "max_hr": current.max_hr,
        "resting_hr": current.resting_hr,
        "timezone_name": current.timezone_name or "UTC",
    }


@router.patch("/profile/heart-rate")
def update_heart_rate_settings(
    data: HeartRateSettingsUpdate,
    current: User = Depends(require_privacy_consent),
    db: Session = Depends(get_db),
):
    fields = data.model_fields_set
    if not fields:
        raise HTTPException(status_code=422, detail="Укажи пульсовые пороги или часовой пояс.")

    next_lthr = data.lthr if "lthr" in fields else current.lthr
    next_max_hr = data.max_hr if "max_hr" in fields else current.max_hr
    next_resting_hr = data.resting_hr if "resting_hr" in fields else current.resting_hr
    next_timezone = data.timezone_name if "timezone_name" in fields else (current.timezone_name or "UTC")
    try:
        ZoneInfo(next_timezone or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Укажи корректный IANA часовой пояс, например Europe/Stockholm.") from exc

    if next_lthr is not None and next_max_hr is not None:
        if not next_lthr < next_max_hr:
            raise HTTPException(status_code=422, detail="LTHR должен быть ниже максимального пульса.")
        if not (0.75 * next_max_hr <= next_lthr <= 0.97 * next_max_hr):
            raise HTTPException(status_code=422, detail="LTHR должен составлять 75–97% от max HR.")
    if next_resting_hr is not None and next_lthr is not None and not next_resting_hr < next_lthr:
        raise HTTPException(status_code=422, detail="Пульс в покое должен быть ниже LTHR.")

    hr_changed = (
        next_lthr != current.lthr
        or next_max_hr != current.max_hr
        or next_resting_hr != current.resting_hr
    )
    if hr_changed:
        from ..services.activity_upload import _settings_day_start_utc
        day_start = _settings_day_start_utc(current)
        changed_today = db.query(HeartRateSettingsHistory.id).filter(
            HeartRateSettingsHistory.user_id == current.id,
            HeartRateSettingsHistory.changed_at >= day_start,
        ).first()
        if changed_today:
            raise HTTPException(status_code=429, detail="Пульсовые настройки можно менять не чаще одного раза в день.")

        current.lthr = next_lthr
        current.max_hr = next_max_hr
        current.resting_hr = next_resting_hr
        db.add(HeartRateSettingsHistory(
            user_id=current.id,
            changed_at=datetime.utcnow(),
            lthr=next_lthr,
            max_hr=next_max_hr,
            resting_hr=next_resting_hr,
        ))

    current.timezone_name = next_timezone or "UTC"
    db.commit()
    db.refresh(current)
    return {
        "lthr": current.lthr,
        "max_hr": current.max_hr,
        "resting_hr": current.resting_hr,
        "timezone_name": current.timezone_name,
        "saved": True,
    }

@router.post("/upload/activity")
@limiter.limit("10/hour", key_func=_upload_rate_key)
async def upload_activity_preview(
    request: Request,
    file: UploadFile = File(...),
    current: User = Depends(require_privacy_consent),
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
        parsed = await _parse_activity_file_bounded(
            content, extension, current.lthr, current.max_hr, current.resting_hr, current.timezone_name
        )
    except TimeoutError as exc:
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
        "file_sha256": hashlib.sha256(content).hexdigest(),
        "expires_at": int(datetime.now(timezone.utc).timestamp()) + PREVIEW_TTL_SECONDS,
        **parsed,
    }
    return {"preview_token": _encode_preview(token_payload), "preview": parsed}


@router.post("/upload/activity/confirm")
@limiter.limit("5/hour", key_func=_upload_rate_key)
def confirm_activity_upload(
    request: Request,
    data: ConfirmUploadInput = Body(...),
    current: User = Depends(require_privacy_consent),
    db: Session = Depends(get_db),
):
    preview = _decode_preview(data.preview_token)
    if preview.get("user_id") != current.id:
        raise HTTPException(status_code=403, detail="Этот предпросмотр создан другим пользователем.")
    required = ("file_sha256", "start_date", "start_date_local", "moving_time", "elapsed_time", "sport_type", "training_load", "intensity")
    if any(key not in preview for key in required):
        raise HTTPException(status_code=422, detail="Предпросмотр неполный. Загрузи файл заново.")

    from ..services.activity_upload import create_activity_from_upload
    from ..services.xp import round_xp

    before_xp = float(current.total_xp or 0)
    status, activity, reason = create_activity_from_upload(
        db,
        current,
        preview,
        str(preview.get("file_sha256") or ""),
        source=UPLOAD_SOURCE,
    )
    if status == "duplicate":
        return JSONResponse(
            status_code=409,
            content={
                "status": "duplicate",
                "existing_activity_id": activity.id if activity else None,
                "reason": reason or "Эта тренировка уже есть, повторно не сохранена.",
            },
        )
    if status == "rejected" or activity is None:
        raise HTTPException(status_code=422, detail=reason or "Не удалось принять тренировку.")

    db.refresh(activity)
    db.refresh(current)
    return {
        "status": "created",
        "message": "Тренировка загружена, XP пересчитан.",
        "activity": {
            "id": activity.id,
            "name": activity.name,
            "source": activity.source,
            "start_date": activity.start_date.isoformat() if activity.start_date else None,
            "start_date_local": activity.start_date_local.isoformat() if activity.start_date_local else None,
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
        "heart_rate_settings": {"lthr": current.lthr, "max_hr": current.max_hr},
        "level": current.level,
    }
