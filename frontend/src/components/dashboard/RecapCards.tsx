"use client";

import { useEffect, useState } from "react";
import { authApi } from "@/lib/auth";
import ShareButton from "@/components/ShareButton";
import { ErrorState, Skeleton } from "@/components/ui";

type WeekRecap = {
  available: boolean;
  finalized?: boolean;
  week_start: string;
  week_end?: string;
  reason?: string;
  total_xp?: number;
  tiles?: Record<string, number>;
  goal_percent?: number;
  target_load?: number;
  actual_load?: number;
  training_days?: number;
  workout_days?: number;
  workouts_count?: number;
  best_day?: { date: string; label: string; xp: number } | null;
  achievements?: { id: number; title: string; xp: number; date?: string | null }[];
  achievements_count?: number;
  league_rank?: number | null;
  league_division?: string | null;
  duel?: { outcome: string; other_name: string; my_xp: number; other_xp: number; is_no_activity_draw: boolean } | null;
};

type SeasonRecap = {
  season: { num: number; flower: string; start: string; end: string };
  state: "interim" | "final";
  is_final: boolean;
  metrics: {
    total_km: number;
    total_hours: number;
    total_elevation: number;
    total_workouts: number;
    total_xp: number;
    best_week: { week_start: string; total_xp: number } | null;
    longest_streak_days: number;
    achievements_count: number;
    best_league_place: { rank: number; week_start: string; division: string | null } | null;
    duels: { wins: number; draws: number; losses: number; played: number };
  };
};

const xp = (value: number | undefined) => Math.round(Number(value) || 0);
const fmt = (value: number | undefined, digits = 1) => Number(value || 0).toLocaleString("ru-RU", { maximumFractionDigits: digits });

function recapDismissed(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function persistDismissed(key: string) {
  try {
    window.localStorage.setItem(key, "1");
  } catch {
    // Private mode or storage restrictions should not block dismissing the banner.
  }
}

export function PreviousWeekRecapBanner() {
  const [recap, setRecap] = useState<WeekRecap | null>(null);
  const [visible, setVisible] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const day = new Date().getDay();
    if (day !== 1 && day !== 2) return;
    let cancelled = false;
    authApi.get("/api/week-recap").then((response) => {
      const value = response.data as WeekRecap;
      if (cancelled || !value?.available || !value.finalized) return;
      setRecap(value);
      setVisible(!recapDismissed(`efl:week-recap-dismissed:${value.week_start}`));
    }).catch(() => {
      if (!cancelled) setError("Не удалось загрузить итоги прошлой недели.");
    });
    return () => { cancelled = true; };
  }, []);

  if (!visible || !recap) return null;
  const close = () => {
    persistDismissed(`efl:week-recap-dismissed:${recap.week_start}`);
    setVisible(false);
  };
  return (
    <section className="relative border-b-2 border-black bg-[#ffd500] p-4 md:p-5" aria-label="Итоги прошлой недели">
      <button type="button" onClick={close} aria-label="Скрыть итоги прошлой недели" className="absolute right-3 top-3 h-8 w-8 border-2 border-black bg-white text-lg font-bold">×</button>
      <div className="flex flex-wrap items-center justify-between gap-2 pr-8">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest">Прошлая неделя · {recap.week_start}</p>
          <button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded} className="mt-1 text-xs font-bold underline underline-offset-2">
            {expanded ? "Свернуть итоги ↑" : "Развернуть итоги ↓"}
          </button>
        </div>
        <span className="font-display text-xl uppercase">+{xp(recap.total_xp)} XP</span>
      </div>
      {expanded && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <p className="min-w-0 text-sm">{fmt(recap.goal_percent)}% цели · {recap.workout_days ?? 0} дней с тренировками{recap.league_rank ? ` · место #${recap.league_rank}` : ""}</p>
          <ShareButton data={{
            kind: "week",
            xp: Number(recap.total_xp || 0),
            weekStart: recap.week_start,
            goalPercent: recap.goal_percent,
            trainingDays: recap.workout_days,
            leagueRank: recap.league_rank,
          }} />
        </div>
      )}
      {error && <p className="mt-2 text-xs">{error}</p>}
    </section>
  );
}

export function WeekRecapCard({ weekStart, userName }: { weekStart: string; userName?: string }) {
  const [recap, setRecap] = useState<WeekRecap | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!weekStart) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setRecap(null);
    authApi.get("/api/week-recap", { params: { week_start: weekStart } }).then((response) => {
      if (cancelled) return;
      const value = response.data as WeekRecap;
      setRecap(value?.available && value.finalized ? value : null);
    }).catch(() => {
      if (!cancelled) setError("Не удалось загрузить итоги выбранной недели.");
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [weekStart, retry]);

  if (loading && !recap) return <section className="border-b-2 border-black bg-white p-4"><Skeleton label="Загружаем итоги недели" rows={2} /></section>;
  if (!recap) return error ? <section className="border-b-2 border-black bg-white p-4"><ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} /></section> : null;

  const tiles = [
    ["Нагрузка", recap.tiles?.effort],
    ["Цель", recap.tiles?.goal],
    ["Регулярность", recap.tiles?.consistency],
    ["Качество", recap.tiles?.quality],
    ["Восстановление", recap.tiles?.recovery],
    ["Квесты и бонусы", recap.tiles?.quests],
  ] as const;
  const duelOutcome = recap.duel
    ? recap.duel.outcome === "win" ? `Победа над ${recap.duel.other_name}`
      : recap.duel.outcome === "loss" ? `Поражение от ${recap.duel.other_name}`
      : "Ничья в дуэли"
    : "";

  return (
    <section className="border-b-2 border-black bg-white p-4 md:p-6" aria-label="Завершённая неделя">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Неделя завершена · {recap.week_start}</p>
          <h3 className="mt-1 font-display text-2xl uppercase">Итоги недели</h3>
          <p className="font-display text-3xl text-[#ff4b26]">+{xp(recap.total_xp)} XP</p>
          <p className="mt-1 text-sm text-[#555]">{fmt(recap.goal_percent)}% цели · {recap.workout_days ?? 0} дней с тренировками · {recap.workouts_count ?? 0} тренировок</p>
        </div>
        <ShareButton data={{
          kind: "week",
          xp: Number(recap.total_xp || 0),
          weekStart: recap.week_start,
          goalPercent: recap.goal_percent,
          trainingDays: recap.workout_days,
          leagueRank: recap.league_rank,
          userName,
        }} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {tiles.map(([label, value]) => (
          <div key={label} className="border border-black/15 bg-[#f4f4f0] p-2">
            <p className="text-[9px] font-bold uppercase tracking-widest text-[#666]">{label}</p>
            <p className="font-display text-lg">+{fmt(value)}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
        <p><strong>Лучший день:</strong> {recap.best_day ? `${recap.best_day.label} · +${xp(recap.best_day.xp)} XP` : "—"}</p>
        <p><strong>Место в лиге:</strong> {recap.league_rank ? `#${recap.league_rank}${recap.league_division ? ` · ${recap.league_division}` : ""}` : "нет результата"}</p>
        <p><strong>Достижения:</strong> {recap.achievements_count ?? 0}</p>
        {duelOutcome && <p><strong>Дуэль:</strong> {duelOutcome} · {xp(recap.duel?.my_xp)}:{xp(recap.duel?.other_xp)} XP</p>}
      </div>
      {(recap.achievements?.length ?? 0) > 0 && (
        <div className="mt-4 border-t border-black/10 pt-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Полученные достижения</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {recap.achievements?.map((item) => <li key={item.id} className="border border-black/20 bg-[#fff9d9] px-2 py-1 text-xs font-bold">{item.title}{item.xp ? ` · +${xp(item.xp)} XP` : ""}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}

function previousSeasonStart(value: string): string {
  const match = /^(\d{4})-(\d{2})-\d{2}$/.exec(value);
  if (!match) return value;
  const previous = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 2, 1));
  return `${previous.getUTCFullYear()}-${String(previous.getUTCMonth() + 1).padStart(2, "0")}-01`;
}

export function SeasonRecapCard({ userName }: { userName?: string }) {
  const [recap, setRecap] = useState<SeasonRecap | null>(null);
  const [currentSeasonStart, setCurrentSeasonStart] = useState("");
  const [selectedSeasonStart, setSelectedSeasonStart] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setRecap(null);
    authApi.get("/api/season/recap", {
      params: selectedSeasonStart ? { season_start: selectedSeasonStart } : {},
    }).then((response) => {
      if (cancelled) return;
      const value = response.data as SeasonRecap;
      setRecap(value);
      if (!currentSeasonStart && !selectedSeasonStart) setCurrentSeasonStart(value.season.start);
    }).catch(() => {
      if (!cancelled) setError("Не удалось загрузить итоги сезона.");
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [selectedSeasonStart, retry]);

  if (loading && !recap) return <section className="border-b-2 border-black bg-white p-4"><Skeleton label="Загружаем итоги сезона" rows={2} /></section>;
  if (!recap) return error ? <section className="border-b-2 border-black bg-white p-4"><ErrorState message={error} onRetry={() => setRetry((value) => value + 1)} /></section> : null;
  const metrics = recap.metrics;
  return (
    <section className="border-b-2 border-black bg-[#f4f4f0] p-4 md:p-6" aria-label="Итоги сезона">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Season {String(recap.season.num).padStart(3, "0")} · {recap.is_final ? "Финальные итоги" : "Промежуточные итоги"}</p>
          <h2 className="mt-1 font-display text-2xl uppercase">Итоги сезона</h2>
          {currentSeasonStart && (
            <label className="mt-2 flex flex-wrap items-center gap-2 text-xs font-bold">
              <span>Период:</span>
              <select value={selectedSeasonStart} onChange={(event) => setSelectedSeasonStart(event.target.value)} className="max-w-full border-2 border-black bg-white px-2 py-1">
                <option value="">Текущий сезон</option>
                <option value={previousSeasonStart(currentSeasonStart)}>Предыдущий сезон</option>
              </select>
            </label>
          )}
          <p className="font-display text-3xl text-[#ff4b26]">+{xp(metrics.total_xp)} XP</p>
        </div>
        <ShareButton data={{
          kind: "season",
          xp: Number(metrics.total_xp || 0),
          totalKm: metrics.total_km,
          totalHours: metrics.total_hours,
          totalElevation: metrics.total_elevation,
          totalWorkouts: metrics.total_workouts,
          bestWeekXp: metrics.best_week?.total_xp,
          longestStreakDays: metrics.longest_streak_days,
          achievementsCount: metrics.achievements_count,
          bestLeagueRank: metrics.best_league_place?.rank,
          duelWins: metrics.duels.wins,
          duelDraws: metrics.duels.draws,
          duelLosses: metrics.duels.losses,
          userName,
        }} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ["Км", fmt(metrics.total_km)],
          ["Часы", fmt(metrics.total_hours)],
          ["Набор, м", fmt(metrics.total_elevation, 0)],
          ["Тренировок", fmt(metrics.total_workouts, 0)],
          ["Лучшая неделя", metrics.best_week ? `+${xp(metrics.best_week.total_xp)} XP` : "—"],
          ["Серия, дней", fmt(metrics.longest_streak_days, 0)],
          ["Достижений", fmt(metrics.achievements_count, 0)],
          ["Лучшее место", metrics.best_league_place ? `#${metrics.best_league_place.rank}` : "—"],
        ].map(([label, value]) => (
          <div key={label} className="border border-black/15 bg-white p-2">
            <p className="text-[9px] font-bold uppercase tracking-widest text-[#666]">{label}</p>
            <p className="font-display text-lg">{value}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-[#555]">Дуэли: {metrics.duels.wins} побед · {metrics.duels.draws} ничьих · {metrics.duels.losses} поражений</p>
    </section>
  );
}
