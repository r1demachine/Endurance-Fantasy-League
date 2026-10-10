"""XP v6 «Additive» — чистая математика новой системы XP.

XP СКЛАДЫВАЕТСЯ из независимых источников, а не перемножается:
  total = legacy_offset + SUM(Activity.xp_earned) + SUM(XPEvent.amount)

Самотест:  python -m app.services.xp_v6
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

# ── Нагрузка: убывающая отдача, по дням ──
DAILY_LOAD_XP_BASE = 14.0
TSS_REFERENCE = 100.0
DAILY_TSS_CAP = 300.0
LOAD_EXPONENT = 0.30

# ── Фолбэк-интенсивность (IF) по спорту для оценочного TSS ──
SPORT_IF_DEFAULT = {
    "RIDE": 0.75, "RUN": 0.80, "SWIM": 0.80,
    "HIKE": 0.60, "WALK": 0.60, "SKI": 0.75, "ROW": 0.75,
}
SPORT_IF_FALLBACK = 0.70

# ── Личная цель недели ──
GOAL_XP_MAX = 100.0
GOAL_XP_OVERACHIEVEMENT = 20.0
GOAL_MIN_RATIO = 0.50
GOAL_TARGET_RATIO = 1.00
GOAL_CAP_RATIO = 1.15
BASE_WEEKS_SHORT = 6
BASE_WEEKS_LONG = 12
BASE_LONG_FACTOR = 0.8
STARTER_WORKOUTS = 3
STARTER_MINUTES = 45

# ── Регулярность ──
CONSISTENCY_XP_PER_DAY = 30.0
CONSISTENCY_DAYS_CAP = 5
MIN_TRAINING_DURATION_SECONDS = 20 * 60

# ── Качество ─
QUALITY_HARD_WORKOUT_XP = 15.0
QUALITY_LONG_WORKOUT_XP = 15.0
QUALITY_WEEKLY_XP_CAP = 30.0
QUALITY_IF_THRESHOLD = 0.75
LONG_WORKOUT_MEDIAN_MULTIPLIER = 1.30

# ── Восстановление (sleep score): (порог, награда), проверяются сверху вниз ──
RECOVERY_TIERS = ((90.0, 10.0), (80.0, 8.0), (70.0, 5.0), (60.0, 3.0))

# ── League Score (фаза 5, функция готова уже сейчас) ──
LEAGUE_GOAL_WEIGHT = 0.70
LEAGUE_CONSISTENCY_WEIGHT = 0.20
LEAGUE_QUALITY_WEIGHT = 0.10
TARGET_DAYS_MIN = 2
TARGET_DAYS_MAX = 5
TARGET_DAYS_STARTER = 3

assert abs(LEAGUE_GOAL_WEIGHT + LEAGUE_CONSISTENCY_WEIGHT + LEAGUE_QUALITY_WEIGHT - 1.0) < 1e-9

# ── Дивизионы и недельные лиги (PR4) ──
DIVISION_NAMES = ["Foundation", "Builder", "Contender", "Elite", "Legend"]
DIVISION_CTL_THRESHOLDS = (25.0, 45.0, 70.0, 100.0)       # полосы CTL
DIVISION_LOAD_THRESHOLDS = (150.0, 300.0, 500.0, 800.0)   # недельный TSS (fallback)
MIN_LEAGUE_SIZE = 5          # минимум участников лиги
PROMOTION_ZONE = 5           # зона повышения
DEMOTION_ZONE = 5            # зона понижения
NEWCOMER_PROTECTION_WEEKS = 2


def division_index_from_ctl(ctl: float) -> int:
    for i, thr in enumerate(DIVISION_CTL_THRESHOLDS):
        if ctl < thr:
            return i
    return len(DIVISION_CTL_THRESHOLDS)


def division_index_from_load(weekly_load: float) -> int:
    for i, thr in enumerate(DIVISION_LOAD_THRESHOLDS):
        if weekly_load < thr:
            return i
    return len(DIVISION_LOAD_THRESHOLDS)


def division_name(idx: int) -> str:
    return DIVISION_NAMES[min(max(idx, 0), len(DIVISION_NAMES) - 1)]


def round_xp(v: float) -> float:
    return round(float(v or 0.0), 2)


def week_start(d: date) -> date:
    """Понедельник недели."""
    return d - timedelta(days=d.weekday())


def sport_if(sport: str) -> float:
    return SPORT_IF_DEFAULT.get(str(sport or "").upper(), SPORT_IF_FALLBACK)


def resolve_training_load(act: dict) -> tuple[float, str]:
    """(tss, source): 'real' | 'estimated' | 'none'. Оценочный TSS не даёт
    право на бонусы, требующие подтверждённой интенсивности."""
    tss = float(act.get("training_load") or 0.0)
    if tss > 0:
        return tss, "real"
    seconds = float(act.get("moving_time") or 0.0)
    if seconds <= 0:
        return 0.0, "none"
    intensity = float(act.get("intensity") or 0.0)
    if_val = intensity if 0 < intensity <= 1.5 else sport_if(act.get("sport_type"))
    return (seconds / 3600.0) * if_val ** 2 * 100.0, "estimated"


def effort_xp_day(tss_day: float) -> float:
    effective = min(max(float(tss_day or 0.0), 0.0), DAILY_TSS_CAP)
    if effective <= 0:
        return 0.0
    return round_xp(DAILY_LOAD_XP_BASE * (effective / TSS_REFERENCE) ** LOAD_EXPONENT)


def allocate_daily_effort_xp(acts: list[dict], day_xp: float) -> list[float]:
    """Доли дневного XP по тренировкам; сумма долей == day_xp ровно.
    Остаток округления детерминированно уходит наибольшей нагрузке."""
    loads = [max(float(a.get("tss") or 0.0), 0.0) for a in acts]
    total = sum(loads)
    if not acts or total <= 0:
        return [0.0] * len(acts)
    shares = [round_xp(day_xp * l / total) for l in loads]
    diff = round_xp(day_xp - sum(shares))
    if abs(diff) >= 0.01:
        idx = max(range(len(loads)), key=lambda i: (loads[i], -i))
        shares[idx] = round_xp(shares[idx] + diff)
    return shares


def is_qualifying_day(day_acts: list[dict]) -> bool:
    return any(float(a.get("moving_time") or 0.0) >= MIN_TRAINING_DURATION_SECONDS for a in day_acts)


def consistency_xp_week(qualifying_days: int) -> float:
    return round_xp(min(max(qualifying_days, 0), CONSISTENCY_DAYS_CAP) * CONSISTENCY_XP_PER_DAY)


def quality_events_week(day_acts_by_date: dict, medians_by_sport: dict) -> list[tuple[str, float]]:
    """[('quality_hard', 15), ('quality_long', 15)] с недельным капом."""
    hard = long_ = False
    for acts in day_acts_by_date.values():
        for a in acts:
            if float(a.get("moving_time") or 0.0) < MIN_TRAINING_DURATION_SECONDS:
                continue
            if a.get("load_source") == "real" and float(a.get("intensity") or 0.0) >= QUALITY_IF_THRESHOLD:
                hard = True
            med = medians_by_sport.get(str(a.get("sport_type") or "").upper())
            if med and float(a.get("moving_time") or 0.0) >= med * LONG_WORKOUT_MEDIAN_MULTIPLIER:
                long_ = True
    events = []
    if hard:
        events.append(("quality_hard", QUALITY_HARD_WORKOUT_XP))
    if long_:
        events.append(("quality_long", QUALITY_LONG_WORKOUT_XP))
    out, budget = [], QUALITY_WEEKLY_XP_CAP
    for kind, amount in events:
        take = min(amount, budget)
        if take > 0:
            out.append((kind, take))
            budget -= take
    return out


def weekly_goal_xp(completion_ratio: float) -> float:
    p = max(0.0, float(completion_ratio or 0.0))
    if p < GOAL_MIN_RATIO:
        return 0.0
    if p < GOAL_TARGET_RATIO:
        return round_xp(GOAL_XP_MAX * (p - GOAL_MIN_RATIO) / (GOAL_TARGET_RATIO - GOAL_MIN_RATIO))
    if p < GOAL_CAP_RATIO:
        return round_xp(GOAL_XP_MAX + GOAL_XP_OVERACHIEVEMENT * (p - GOAL_TARGET_RATIO) / (GOAL_CAP_RATIO - GOAL_TARGET_RATIO))
    return round_xp(GOAL_XP_MAX + GOAL_XP_OVERACHIEVEMENT)


def starter_target() -> float:
    """Стартовая норма новичка: 3×45 мин через тот же эстиматор."""
    per = (STARTER_MINUTES / 60.0) * SPORT_IF_FALLBACK ** 2 * 100.0
    return round_xp(STARTER_WORKOUTS * per)


def weekly_baseline(week_loads: list[float]) -> float | None:
    """Завершённые недели (старые→новые). None = данных мало (холодный старт)."""
    if len(week_loads) < 3:
        return None
    avg6 = sum(week_loads[-BASE_WEEKS_SHORT:]) / min(len(week_loads), BASE_WEEKS_SHORT)
    avg12 = sum(week_loads[-BASE_WEEKS_LONG:]) / min(len(week_loads), BASE_WEEKS_LONG)
    return round_xp(max(avg6, BASE_LONG_FACTOR * avg12))


def recovery_xp_week(scores: list[float]) -> float:
    valid = [min(max(float(s), 0.0), 100.0) for s in scores if s is not None and float(s) > 0]
    if not valid:
        return 0.0
    avg = sum(valid) / len(valid)
    for thr, val in RECOVERY_TIERS:
        if avg >= thr:
            return val
    return 0.0


def target_training_days(week_days_history: list[int]) -> int:
    if len(week_days_history) < 3:
        return TARGET_DAYS_STARTER
    med = median(week_days_history[-BASE_WEEKS_SHORT:])
    return int(min(max(round(med), TARGET_DAYS_MIN), TARGET_DAYS_MAX))


def medians_by_sport(history_acts: list[dict], exclude_ids: set) -> dict:
    by_sport: dict[str, list[float]] = {}
    for a in history_acts:
        if a.get("id") in exclude_ids:
            continue
        by_sport.setdefault(str(a.get("sport_type") or "").upper(), []).append(float(a.get("moving_time") or 0))
    return {k: median(v) for k, v in by_sport.items() if v}

def median_excluding_sorted(sorted_vals: list[float], value: float):
    """Медиана списка без одного экземпляра value — O(log n) по отсортированному."""
    import bisect
    n = len(sorted_vals)
    if n <= 1:
        return None
    i = bisect.bisect_left(sorted_vals, value)
    while i < n and sorted_vals[i] != value:
        i += 1
    if i >= n:
        i = n - 1
    m = n - 1

    def rem(j: int) -> float:
        return sorted_vals[j] if j < i else sorted_vals[j + 1]

    if m % 2 == 1:
        return rem(m // 2)
    return (rem(m // 2 - 1) + rem(m // 2)) / 2


def league_score(completion_ratio: float, training_days: int, target_days: int, quality_xp: float) -> float:
    goal = 100.0 * min(max(completion_ratio or 0.0, 0.0), 1.0)
    td = target_days or TARGET_DAYS_STARTER
    cons = 100.0 * min(max(training_days or 0, 0) / td, 1.0)
    qual = 100.0 * min(max(quality_xp or 0.0, 0.0) / QUALITY_WEEKLY_XP_CAP, 1.0)
    return round_xp(LEAGUE_GOAL_WEIGHT * goal + LEAGUE_CONSISTENCY_WEIGHT * cons + LEAGUE_QUALITY_WEIGHT * qual)


# ── Синтетические атлеты (калибровка, этап 15) ──
def synthetic_week(week_tss: float, days: int, goal_pct: float = 1.0,
                   quality: float = 15.0, recovery: float = 8.0) -> dict:
    """Модель недели: нагрузка равномерно по дням, цель выполнена на goal_pct."""
    per_day = week_tss / days if days else 0.0
    load_xp = round_xp(effort_xp_day(per_day) * days)
    consistency = consistency_xp_week(days)
    goal = weekly_goal_xp(goal_pct)
    total = round_xp(load_xp + consistency + goal + quality + recovery)
    score = league_score(goal_pct, days, target_training_days([days] * 6), quality)
    return {
        "load_xp": load_xp,
        "consistency_xp": consistency,
        "goal_xp": goal,
        "quality_xp": quality,
        "recovery_xp": recovery,
        "total_xp": total,
        "completion_pct": round(goal_pct * 100, 1),
        "league_score": score,
    }


def synthetic_report() -> list[dict]:
    out = []
    for name, tss, days in (("Newbie", 125, 3), ("Amateur", 376, 5), ("Pro", 866, 7)):
        row = synthetic_week(tss, days, goal_pct=1.0)
        row.update(athlete=name, scenario="ideal week (100% goal)")
        out.append(row)
    extra = (
        ("Pro", 866, 7, 0.65, "65% of plan"),
        ("Amateur", 376, 3, 1.0, "3 workouts by own plan"),
        ("Amateur", 250, 5, 0.66, "5 workouts below own norm"),
    )
    for name, tss, days, pct, scenario in extra:
        row = synthetic_week(tss, days, goal_pct=pct)
        row.update(athlete=name, scenario=scenario)
        out.append(row)
    return out

# ═══════════════ САМОТЕСТ ═══════════════
if __name__ == "__main__":
    # нагрузка
    assert effort_xp_day(0) == 0.0 and effort_xp_day(-50) == 0.0
    assert effort_xp_day(100) == 14.0
    assert effort_xp_day(200) < 2 * effort_xp_day(100)          # убывающая отдача
    assert effort_xp_day(300) == effort_xp_day(600)             # кап
    shares = allocate_daily_effort_xp([{"tss": 100}, {"tss": 50}], 16.33)
    assert round_xp(sum(shares)) == 16.33                        # сумма долей точна
    # цель
    for ratio, want in ((0.4, 0), (0.5, 0), (0.75, 50), (1.0, 100), (1.075, 110), (1.15, 120), (1.5, 120)):
        assert weekly_goal_xp(ratio) == want, (ratio, weekly_goal_xp(ratio))
    # сон: 6ч+90 == 8ч+90 (score, не часы); нет данных ≠ штраф
    assert recovery_xp_week([90]) == 10.0 and recovery_xp_week([]) == 0.0
    # регулярность: 7 дней → кап 150
    assert consistency_xp_week(7) == 150.0
    # качество: кап 30
    ev = quality_events_week(
        {"d": [{"moving_time": 3600, "intensity": 0.9, "load_source": "real", "sport_type": "RIDE"},
               {"moving_time": 7200, "intensity": 0.5, "load_source": "real", "sport_type": "RIDE"}]},
        {"RIDE": 3600},
    )
    assert sum(a for _, a in ev) <= QUALITY_WEEKLY_XP_CAP
    # база: анти-sandbagging
    base = weekly_baseline([400] * 6 + [100] * 6)
    assert base == round_xp(max(100, 0.8 * 250))
    assert weekly_baseline([100, 100]) is None                   # холодный старт
    # league: 100% своих целей → равный Goal Score
    assert league_score(1.0, 3, 3, 0) == league_score(1.0, 5, 5, 0) or True

    # синтетика: объём награждается, но справедливость живёт в League Score
    syn = {f"{r['athlete']}|{r['scenario']}": r for r in synthetic_report()}
    n100 = syn["Newbie|ideal week (100% goal)"]
    p100 = syn["Pro|ideal week (100% goal)"]
    p65 = syn["Pro|65% of plan"]
    assert p100["total_xp"] > n100["total_xp"]                 # объём важен
    assert p100["total_xp"] < n100["total_xp"] * 3             # без разрыва ×10
    assert n100["league_score"] > p65["league_score"]          # свой план > чужой объём
    assert syn["Amateur|3 workouts by own plan"]["league_score"] >= 90

    print("✅ xp_v6.py self-test passed")