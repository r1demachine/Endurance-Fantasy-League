"""Единая система начисления XP. Все расчёты — чистые функции (легко тестировать).

Итог: XP = baseXP(длительность) × sleepMult × intensityMult × streakMult

Интенсивность:
  • цепочка HIGH/MEDIUM двигается по МАКСИМУМУ дня (анти-фарм по календарным дням);
  • множитель и категория каждой тренировки считаются по ЕЁ собственному IF;
  • позиционный штраф/бонус цепочки применяется только к тренировкам, чья
    категория == ведущая категория дня; слабее ведущей -> базовый множитель.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

# ─────────────────────────────────────────────────────────────
# 1. БАЗОВЫЙ XP ЗА ДЛИТЕЛЬНОСТЬ
# ─────────────────────────────────────────────────────────────
RUN_RATE = 25.0
BIKE_RATE = 25.0
SWIM_RATE = 25.0
DEFAULT_RATE = 15.0

_RUN_WORDS = {"RUN", "RUNNING", "TRAILRUN", "TRAILRUNNING"}
_BIKE_WORDS = {"RIDE", "RIDING", "CYCLE", "CYCLING", "BIKE", "MOUNTAINBIKE",
               "ROADBIKE", "GRAVEL", "BMX", "EBIKE", "E_BIKE", "VIRTUALRIDE",
               "INDOORCYCLING", "CYCLOCROSS"}
_SWIM_WORDS = {"SWIM", "SWIMMING", "POOLSWIM", "OPENWATER", "SWIMMINGPOOL"}


def duration_rate(sport_type: str | None) -> float:
    s = (sport_type or "").upper().replace(" ", "").replace("_", "")
    if s in _RUN_WORDS:
        return RUN_RATE
    if s in _BIKE_WORDS:
        return BIKE_RATE
    if s in _SWIM_WORDS:
        return SWIM_RATE
    return DEFAULT_RATE


def base_xp_from_duration(sport_type: str | None, moving_time_s: int | float | None) -> float:
    hours = (float(moving_time_s or 0)) / 3600.0
    return round(hours * duration_rate(sport_type), 2)


# ─────────────────────────────────────────────────────────────
# 2. МНОЖИТЕЛЬ СНА (чистая функция)
# ─────────────────────────────────────────────────────────────
SLEEP_PEAK_HOURS = 8.0
SLEEP_FALL_SLOPE_HOURS = 12.0   # спуск ×2→×1 занимает 12 ч (8→20), далее clamp 1.0


def sleep_multiplier(sleep_secs: int | float | None) -> float:
    if not sleep_secs or sleep_secs <= 0:
        return 1.0
    h = float(sleep_secs) / 3600.0
    if h <= SLEEP_PEAK_HOURS:
        mult = 1.0 + h / SLEEP_PEAK_HOURS
    else:
        mult = 2.0 - (h - SLEEP_PEAK_HOURS) / SLEEP_FALL_SLOPE_HOURS
        if mult < 1.0:
            mult = 1.0
    return round(max(1.0, min(2.0, mult)), 2)


# ─────────────────────────────────────────────────────────────
# 3. ИНТЕНСИВНОСТЬ: нормализация + источник + категории + шаг цепочки
# ─────────────────────────────────────────────────────────────
def normalize_intensity(value) -> float:
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    if v > 3.0:
        v = v / 100.0
    if v < 0.0:
        v = 0.0
    if v > 1.0:
        v = 1.0
    return round(v, 4)


def resolve_intensity(raw, training_load=None, moving_time=None):
    """(value_или_None, source). None = данных нет (не путать с реальным низким IF)."""
    if raw is not None and raw != 0:
        return normalize_intensity(raw), "icu_intensity"
    try:
        tl = float(training_load or 0)
        s = float(moving_time or 0)
    except (TypeError, ValueError):
        tl = s = 0.0
    if tl > 0 and s > 0:
        ifr = math.sqrt(tl * 36.0 / s)   # IF из TSS при часовой ёмкости H=1ч
        if ifr > 0:
            return normalize_intensity(ifr), "training_load"
    return None, "none"


def intensity_category_from(value) -> str:
    if value is None:
        return "UNKNOWN"
    if value <= 0.55:
        return "LOW"
    if value < 0.76:
        return "MEDIUM"
    return "HIGH"


_INTENSITY_MULT = {1: 1.5, 2: 1.0, 3: 0.5}   # позиции HIGH подряд


def _base_mult_for(cat: str) -> tuple[float, str]:
    """Базовый множитель категории (1-я позиция цепочки)."""
    if cat == "HIGH":
        return 1.5, "высокая интенсивность"
    if cat == "MEDIUM":
        return 1.5, "средняя интенсивность"
    if cat == "LOW":
        return 1.2, "низкая интенсивность — восстановительный день"
    return 1.0, "нет данных об интенсивности → ×1.0"   # UNKNOWN


def _intensity_step(resolved_value, high_run: int, medium_run: int):
    """Один календарный день по МАКСИМУМУ. Возвращает 6 значений:
    (lead_mult, lead_reason, new_high_run, new_medium_run, lead_cat, pos_info).
    pos_info = None | ("HIGH", pos) | ("MEDIUM", mr)."""
    cat = intensity_category_from(resolved_value)
    if cat == "UNKNOWN":
        return 1.0, "нет данных об интенсивности → ×1.0", 0, 0, cat, None
    if cat == "LOW":
        # LOW как максимум дня прерывает обе цепочки
        return 1.2, "низкая интенсивность — восстановительный день", 0, 0, cat, None
    if cat == "HIGH":
        hr = high_run + 1
        pos = ((hr - 1) % 3) + 1
        mult = _INTENSITY_MULT[pos]
        reason = f"{pos}-й день высокой интенсивности подряд" if pos > 1 else "высокая интенсивность"
        return mult, reason, hr, 0, cat, ("HIGH", pos)
    # MEDIUM
    mr = medium_run + 1
    mult = 1.5 if mr <= 3 else 1.3
    reason = (f"{mr}-й день средней интенсивности подряд (×1.3 — длительный MEDIUM)"
              if mr >= 4 else "средняя интенсивность")
    return mult, reason, 0, mr, cat, ("MEDIUM", mr)


def _mult_for_training(tc: str, lead_cat: str, lead_mult: float, lead_reason: str, pos_info):
    """Множитель КОНКРЕТНОЙ тренировки: позиционный, если она == ведущая категория дня;
    иначе её честный базовый множитель."""
    if tc == lead_cat and pos_info is not None:
        return lead_mult, lead_reason
    return _base_mult_for(tc)


# ─────────────────────────────────────────────────────────────
# ОКРУГЛЕНИЕ (единое место)
# ─────────────────────────────────────────────────────────────
def round_xp(value: float) -> float:
    return round(float(value), 2)


def level_from_xp(total_xp: float) -> int:
    return int((max(0.0, float(total_xp or 0)) / 100.0) ** 0.5) + 1


# ─────────────────────────────────────────────────────────────
# РАЗБИВКА ДНЯ (per-тренировка)
# ─────────────────────────────────────────────────────────────
def compute_day_xp_breakdown(activities_of_day: list[dict], lead_cat: str,
                             lead_mult: float, lead_reason: str, pos_info,
                             streak_mult: float, streak_reason: str,
                             sleep_secs) -> list[dict]:
    out = []
    for a in activities_of_day:
        base = base_xp_from_duration(a.get("sport_type"), a.get("moving_time"))
        smult = sleep_multiplier(sleep_secs)
        val, _src = resolve_intensity(a.get("intensity"), a.get("training_load"), a.get("moving_time"))
        tc = intensity_category_from(val)
        imult, ireason = _mult_for_training(tc, lead_cat, lead_mult, lead_reason, pos_info)
        xp = round_xp(base * smult * imult * streak_mult)
        out.append({
            **a,
            "base_xp": base,
            "rate_per_hour": duration_rate(a.get("sport_type")),
            "sleep_multiplier": smult,
            "intensity_multiplier": imult,
            "intensity_category": tc,
            "intensity_reason": ireason,
            "streak_multiplier": streak_mult,
            "streak_reason": streak_reason,
            "xp_earned": xp,
        })
    return out


# ─────────────────────────────────────────────────────────────
# ГЛАВНЫЙ ПЕРЕСЧЁТ ПО КАЛЕНДАРНЫМ ДНЯМ
# ─────────────────────────────────────────────────────────────
def recalculate_timeline(day_records: list[dict]) -> list[dict]:
    """day_records: отсортированный по дате список
        {"date": date, "is_train": bool, "sleep_secs": ..., "activities": [...]}
    TRAIN-дням добавляет day_category/intensity_multiplier/intensity_reason/_pos_info,
    затем streak_multiplier/streak_reason и пересчитанные activities[] per-тренировка."""

    # --- проход 1: интенсивность по МАКСИМУМУ дня, цепочки двигаются здесь ---
    high_run = medium_run = 0
    for d in day_records:
        if not d["is_train"]:
            high_run = medium_run = 0
            continue
        resolved = [
            resolve_intensity(a.get("intensity"), a.get("training_load"), a.get("moving_time"))[0]
            for a in d["activities"]
        ]
        real = [v for v in resolved if v is not None]
        day_value = max(real) if real else None
        lead_mult, lead_reason, high_run, medium_run, lead_cat, pos_info = _intensity_step(
            day_value, high_run, medium_run)
        d["day_category"] = lead_cat
        d["intensity_multiplier"] = lead_mult      # ведущий множитель дня (для отладки)
        d["intensity_reason"] = lead_reason
        d["_pos_info"] = pos_info

    # --- проход 2: дневной streak + per-тренировка разбивка ---
    rest_run = 0
    recover_left = 0
    recover_factor = 1.0
    trained_after_rest = False
    hard_pending = False
    for d in day_records:
        if not d["is_train"]:
            rest_run += 1
            if trained_after_rest:
                hard_pending = True
            continue
        gap = rest_run
        rest_run = 0
        if hard_pending:
            mult, reason = 1.0, "повторный пропуск → жёсткий сброс streak"
            recover_left, recover_factor = 2, 1.0
            hard_pending = False
            trained_after_rest = True
        elif recover_left > 0:
            mult, reason = recover_factor, f"восстановление streak (×{recover_factor})"
            recover_left -= 1
            trained_after_rest = (gap >= 1)
        elif gap == 0:
            mult, reason = 2.0, "активный дневной streak"
            trained_after_rest = False
        elif gap == 1:
            mult, reason = 2.0, "защитный день пропуска — streak сохранён"
            trained_after_rest = True
        elif gap == 2:
            mult, reason = 1.5, "2 дня пропуска → восстановление streak"
            recover_left, recover_factor = 1, 1.5
            trained_after_rest = True
        else:
            mult, reason = 1.0, "3+ дня пропуска → сброс streak"
            recover_left, recover_factor = 2, 1.0
            trained_after_rest = True
        d["streak_multiplier"] = mult
        d["streak_reason"] = reason

        d["activities"] = compute_day_xp_breakdown(
            d["activities"], d["day_category"], d["intensity_multiplier"], d["intensity_reason"],
            d.get("_pos_info"), mult, reason, d.get("sleep_secs"),
        )
    return day_records


# ─────────────────────────────────────────────────────────────
# АВТОТЕСТЫ (запуск: python -m app.services.xp)
# ─────────────────────────────────────────────────────────────
def _self_test():
    # сон
    assert sleep_multiplier(None) == 1.0
    assert sleep_multiplier(0) == 1.0
    assert sleep_multiplier(2 * 3600) == 1.25
    assert sleep_multiplier(4 * 3600) == 1.5
    assert sleep_multiplier(6 * 3600) == 1.75
    assert sleep_multiplier(8 * 3600) == 2.0
    assert sleep_multiplier(12 * 3600) == 1.67
    assert sleep_multiplier(16 * 3600) == 1.33
    assert sleep_multiplier(24 * 3600) == 1.0
    # базовый XP
    assert base_xp_from_duration("RUN", 1800) == 12.5
    assert base_xp_from_duration("RUN", 3600) == 25.0
    assert base_xp_from_duration("RUN", 5400) == 37.5
    assert base_xp_from_duration("WORKOUT", 3600) == 15.0
    # категории
    assert intensity_category_from(None) == "UNKNOWN"
    assert intensity_category_from(0.0) == "LOW"
    assert intensity_category_from(0.55) == "LOW"
    assert intensity_category_from(0.56) == "MEDIUM"
    assert intensity_category_from(0.75) == "MEDIUM"
    assert intensity_category_from(0.76) == "HIGH"
    assert intensity_category_from(1.2) == "HIGH"
    assert intensity_category_from(85) == "HIGH"
    # resolve
    assert resolve_intensity(0.8, 100, 3600)[0] == 0.8
    assert resolve_intensity(0.8, 100, 3600)[1] == "icu_intensity"
    assert abs(resolve_intensity(None, 100, 3600)[0] - 1.0) < 0.01
    assert resolve_intensity(None, 100, 3600)[1] == "training_load"
    assert abs(resolve_intensity(None, 50, 3600)[0] - 0.71) < 0.02
    assert resolve_intensity(None, None, None)[0] is None
    assert resolve_intensity(0, 0, 3600)[0] is None
    # шаг цепочки -> 6 значений с pos_info
    step = _intensity_step(0.8, 0, 0)
    assert len(step) == 6 and step[4] == "HIGH" and step[5] == ("HIGH", 1)
    step_u = _intensity_step(None, 0, 0)
    assert len(step_u) == 6 and step_u[4] == "UNKNOWN" and step_u[0] == 1.0 and step_u[5] is None
    # пример ТЗ: 60 мин бег, 8ч сон, 1-й HIGH, активный streak = 150
    one = compute_day_xp_breakdown(
        [{"sport_type": "RUN", "moving_time": 3600, "intensity": 0.8}],
        "HIGH", 1.5, "высокая интенсивность", ("HIGH", 1), 2.0, "активный дневной streak", 8 * 3600)
    assert one[0]["xp_earned"] == 150.0, one[0]["xp_earned"]
    # пример ТЗ: 60 мин сила, 4ч сон, 3-й HIGH, streak после 3 пропусков = 11.25
    two = compute_day_xp_breakdown(
        [{"sport_type": "WORKOUT", "moving_time": 3600, "intensity": 0.8}],
        "HIGH", 0.5, "3-й день...", ("HIGH", 3), 1.0, "3+ дня пропуска...", 4 * 3600)
    assert two[0]["xp_earned"] == 11.25, two[0]["xp_earned"]

    # === НОВОЕ: две тренировки в день -> разные множители, цепочка по максимуму ===
    days = recalculate_timeline([
        {"date": date(2026, 1, 1), "is_train": True, "sleep_secs": 8 * 3600, "activities": [
            {"id": 1, "sport_type": "RIDE", "moving_time": 3600, "intensity": 0.9, "training_load": 0},
            {"id": 2, "sport_type": "RIDE", "moving_time": 3600, "intensity": 0.4, "training_load": 0},
        ]},
    ])
    a1, a2 = days[0]["activities"]
    assert a1["intensity_category"] == "HIGH" and a1["intensity_multiplier"] == 1.5
    assert a2["intensity_category"] == "LOW" and a2["intensity_multiplier"] == 1.2
    assert a1["streak_multiplier"] == a2["streak_multiplier"]          # streak одинаков на день
    assert a1["xp_earned"] == 150.0 and a2["xp_earned"] == 120.0       # 25*2*1.5*2 и 25*2*1.2*2

    # === LOW как максимум дня прерывает HIGH-цепочку ===
    days = recalculate_timeline([
        {"date": date(2026, 1, 1), "is_train": True, "sleep_secs": None, "activities": [
            {"id": 1, "sport_type": "RIDE", "moving_time": 3600, "intensity": 0.9, "training_load": 0}]},
        {"date": date(2026, 1, 2), "is_train": True, "sleep_secs": None, "activities": [
            {"id": 2, "sport_type": "RIDE", "moving_time": 3600, "intensity": 0.4, "training_load": 0}]},
        {"date": date(2026, 1, 3), "is_train": True, "sleep_secs": None, "activities": [
            {"id": 3, "sport_type": "RIDE", "moving_time": 3600, "intensity": 0.9, "training_load": 0}]},
    ])
    assert days[0]["activities"][0]["intensity_multiplier"] == 1.5     # HIGH pos1
    assert days[1]["activities"][0]["intensity_multiplier"] == 1.2     # LOW-день
    assert days[2]["activities"][0]["intensity_multiplier"] == 1.5     # HIGH pos1 снова

    # === LOW-тренировка ВНУТРИ HIGH-дня НЕ прерывает цепочку (максимум дня = HIGH) ===
    days = recalculate_timeline([
        {"date": date(2026, 1, 1), "is_train": True, "sleep_secs": None, "activities": [
            {"id": 1, "sport_type": "RIDE", "moving_time": 3600, "intensity": 0.9, "training_load": 0},
            {"id": 2, "sport_type": "RIDE", "moving_time": 3600, "intensity": 0.4, "training_load": 0}]},
        {"date": date(2026, 1, 2), "is_train": True, "sleep_secs": None, "activities": [
            {"id": 3, "sport_type": "RIDE", "moving_time": 3600, "intensity": 0.9, "training_load": 0}]},
    ])
    assert days[0]["activities"][0]["intensity_multiplier"] == 1.5     # HIGH pos1
    assert days[0]["activities"][1]["intensity_multiplier"] == 1.2     # LOW честный базовый
    assert days[1]["activities"][0]["intensity_multiplier"] == 1.0     # HIGH pos2 (цепочка НЕ сбросилась)

    print("✅ xp.py self-test passed")


if __name__ == "__main__":
    _self_test()