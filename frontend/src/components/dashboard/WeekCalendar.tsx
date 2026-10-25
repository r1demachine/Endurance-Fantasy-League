"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  Bike,
  ChevronLeft,
  ChevronRight,
  Dumbbell,
  Footprints,
  Waves,
  X,
} from "lucide-react";
import ActivityXpDetails, { type ActivityXpContext } from "@/components/ActivityXpDetails";
import ActivitySocial from "@/components/ActivitySocial";
import ShareButton from "@/components/ShareButton";
import { EmptyState } from "@/components/ui";
import { formatWeekRange } from "@/lib/format";
import { formatActivityDuration, formatSleepDuration, getCalendarWeekDates } from "@/lib/week-calendar";
import TrainingGlossary from "@/components/dashboard/TrainingGlossary";

type WeekOption = { week_start: string; label: string };
type Wellness = {
  sleep_secs?: number | null;
  sleep_score?: number | null;
  hrv?: number | null;
  resting_hr?: number | null;
};
type DayActivity = ActivityXpContext & {
  name: string;
  sport: string;
  moving_time_min: number;
  distance_km: number;
  xp: number;
  tss?: number | null;
  tss_estimated?: boolean;
  is_manual?: boolean;
  is_indoor?: boolean;
  likes_count?: number;
  comments_count?: number;
};
type DayLedger = {
  date: string;
  wellness?: Wellness;
  activities?: DayActivity[];
  xp?: { effort?: number; bonuses?: { title: string; amount: number }[]; total?: number };
  qualifying?: boolean;
  rest_day?: boolean;
};
type WeekBonus = { title: string; amount: number };

type Props = {
  weekLoading: boolean;
  weekData: any;
  weekOptions: WeekOption[];
  selectedWeekStart: string;
  onWeekChange: (weekStart: string) => void;
  onOpenSources: () => void;
  initialActivityId?: number | null;
  userName?: string;
  restDayState?: { today: string; available: boolean; used_this_week: boolean; reason?: string | null };
  restDayBusy?: boolean;
  restDayMessage?: string;
  restDayError?: string;
  onUseRestDay?: () => void;
};

function dateFromIso(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]) - 1;
  const day = Number(match[3]);
  const result = new Date(year, month, day, 12);
  return result.getFullYear() === year && result.getMonth() === month && result.getDate() === day
    ? result
    : null;
}

function toIsoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDistance(km: number): string {
  return Number(km || 0).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

function presentNumber(value: number | null | undefined, suffix: string): string | null {
  if (value === null || value === undefined) return null;
  return `${Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}${suffix}`;
}

function SportIcon({ sport }: { sport: string }) {
  const normalized = sport.toLowerCase();
  if (/bike|cycling|ride|вел|велосипед/.test(normalized)) return <Bike aria-hidden="true" size={16} />;
  if (/run|walk|hike|бег|ходьб/.test(normalized)) return <Footprints aria-hidden="true" size={16} />;
  if (/swim|плаван/.test(normalized)) return <Waves aria-hidden="true" size={16} />;
  if (/strength|weight|gym|силов|тренаж/.test(normalized)) return <Dumbbell aria-hidden="true" size={16} />;
  return <Activity aria-hidden="true" size={16} />;
}

function DayHeading({ day, isToday, userName }: { day: DayLedger; isToday: boolean; userName?: string }) {
  const parsed = dateFromIso(day.date);
  const weekday = parsed
    ? new Intl.DateTimeFormat("ru-RU", { weekday: "short" }).format(parsed)
    : "день";
  const dayNumber = parsed ? String(parsed.getDate()) : day.date.slice(-2);
  return (
    <div className={`flex min-w-0 items-center justify-between gap-2 border-b-2 border-black px-3 py-2 ${isToday ? "bg-[#ffd500]" : "bg-[#f4f4f0]"}`}>
      <div className="min-w-0">
        <h3 id={`day-${day.date}`} className="truncate text-xs font-black uppercase tracking-widest">{weekday}</h3>
        <p className="text-[10px] font-bold text-[#555]">{day.date}</p>
        <div className="mt-1">
          <ShareButton label="День" data={{
            kind: "day",
            xp: Number(day.xp?.total) || (day.activities ?? []).reduce((sum, activity) => sum + Number(activity.xp || 0), 0),
            date: day.date,
            workoutCount: day.activities?.length ?? 0,
            userName,
          }} />
        </div>
      </div>
      <span
        className="inline-flex h-9 w-9 shrink-0 items-center justify-center border-2 border-black bg-white font-display text-base tabular-nums whitespace-nowrap leading-none"
        style={{ whiteSpace: "nowrap", wordBreak: "normal", overflowWrap: "normal" }}
        aria-label={isToday ? "Сегодня" : dayNumber}
        title={isToday ? "Сегодня" : undefined}
      >
        {dayNumber}
      </span>
    </div>
  );
}

function HealthStrip({ wellness }: { wellness: Wellness }) {
  const chips: { label: string; value: string }[] = [];
  if (wellness.sleep_secs !== null && wellness.sleep_secs !== undefined) {
    chips.push({ label: "Сон", value: formatSleepDuration(Number(wellness.sleep_secs)) });
  }
  const score = presentNumber(wellness.sleep_score, "");
  if (score !== null) chips.push({ label: "Sleep score", value: score });
  const hrv = presentNumber(wellness.hrv, " мс");
  if (hrv !== null) chips.push({ label: "HRV", value: hrv });
  const resting = presentNumber(wellness.resting_hr, " уд/мин");
  if (resting !== null) chips.push({ label: "Пульс покоя", value: resting });

  if (chips.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 border-b border-black/10 px-2 py-2">
      {chips.map((chip) => (
        <span
          key={chip.label}
          className="inline-flex min-w-0 max-w-full items-baseline gap-1 border border-black/20 bg-white px-1.5 py-1 text-[10px] leading-tight"
        >
          <span className="text-[#666]">{chip.label}</span>
          <strong className="whitespace-nowrap">{chip.value}</strong>
        </span>
      ))}
    </div>
  );
}

function WorkoutTile({
  activity,
  onOpen,
  disabled,
}: {
  activity: DayActivity;
  onOpen: (activity: DayActivity, trigger: HTMLButtonElement) => void;
  disabled: boolean;
}) {
  const xp = Number(activity.xp ?? activity.effort_xp ?? 0);
  const tss = activity.tss === null || activity.tss === undefined
    ? null
    : Math.round(Number(activity.tss));
  const ariaLabel = [
    activity.name,
    activity.sport,
    formatActivityDuration(activity.moving_time_min),
    `${formatDistance(activity.distance_km)} км`,
    tss === null ? null : `TSS ${tss}`,
    `плюс ${Math.round(xp)} XP`,
    activity.tss_estimated ? "оценочная нагрузка" : null,
    activity.is_manual ? "ручная запись" : null,
    activity.is_indoor ? "тренировка на станке" : null,
    "открыть подробный разбор XP",
  ].filter(Boolean).join(", ");

  return (
    <button
      type="button"
      onClick={(event) => onOpen(activity, event.currentTarget)}
      disabled={disabled}
      aria-label={ariaLabel}
      className="group block w-full min-w-0 border-2 border-black bg-white p-2 text-left shadow-[2px_2px_0_#111] transition-transform hover:-translate-y-0.5 hover:bg-[#fff9d9] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2] motion-reduce:transform-none motion-reduce:transition-none disabled:cursor-default"
    >
      <div className="flex min-w-0 items-start gap-1.5">
        <span className="mt-0.5 shrink-0 text-[#5866f2]"><SportIcon sport={activity.sport} /></span>
        <span className="min-w-0 break-words text-xs font-bold leading-snug">{activity.name || "Без названия"}</span>
      </div>
      <p className="mt-1 text-[10px] leading-snug text-[#555]">
        {formatActivityDuration(activity.moving_time_min)} · {formatDistance(activity.distance_km)} км
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        {tss !== null && <span className="border border-black/20 bg-[#f4f4f0] px-1 py-0.5 text-[10px] font-bold">TSS {tss}</span>}
        <span className="border border-[#16a34a]/40 bg-[#e9f8ee] px-1 py-0.5 text-[10px] font-black text-[#166534]">+{Math.round(xp)} XP</span>
      </div>
      <p className="mt-1 text-[9px] font-bold tracking-wide text-[#666]">
        ♥ {Math.max(0, Number(activity.likes_count) || 0)} · 💬 {Math.max(0, Number(activity.comments_count) || 0)}
      </p>
      {(activity.tss_estimated || activity.is_manual || activity.is_indoor) && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {activity.tss_estimated && <span className="bg-[#ff4b26] px-1 py-0.5 text-[9px] font-black text-white">EST</span>}
          {activity.is_manual && <span className="border border-black/30 px-1 py-0.5 text-[9px] font-bold">РУЧНАЯ</span>}
          {activity.is_indoor && <span className="border border-black/30 px-1 py-0.5 text-[9px] font-bold">СТАНОК</span>}
        </div>
      )}
    </button>
  );
}

function DayColumn({
  day,
  isToday,
  isFuture,
  onOpenActivity,
  userName,
  canUseRestDay = false,
  restDayBusy = false,
  onUseRestDay,
}: {
  day: DayLedger;
  isToday: boolean;
  isFuture: boolean;
  onOpenActivity: (activity: DayActivity, trigger: HTMLButtonElement) => void;
  userName?: string;
  canUseRestDay?: boolean;
  restDayBusy?: boolean;
  onUseRestDay?: () => void;
}) {
  const activities = day.activities ?? [];
  return (
    <article
      aria-labelledby={`day-${day.date}`}
      className={`flex min-w-0 flex-col border-2 border-black bg-white ${isFuture ? "opacity-45" : ""} ${isToday ? "ring-2 ring-[#5866f2] ring-offset-2" : ""}`}
    >
      <DayHeading day={day} isToday={isToday} userName={userName} />
      <div className="min-w-0 flex-1">
        <HealthStrip wellness={day.wellness ?? {}} />
        <div className="space-y-2 p-2">
          {activities.map((activity) => (
            <WorkoutTile
              key={activity.id}
              activity={activity}
              onOpen={onOpenActivity}
              disabled={isFuture}
            />
          ))}
          {activities.length === 0 && (
            <p className="px-1 py-3 text-center text-[10px] text-[#777]">{isFuture ? "Впереди" : day.rest_day ? "День отдыха" : "Нет тренировок"}</p>
          )}
        </div>
      </div>
      <div className="border-t-2 border-black bg-[#f4f4f0] px-2 py-2">
        <p className="text-[9px] font-bold uppercase tracking-wide text-[#666]">Итого за день</p>
        <p className="font-display text-base text-[#ff4b26]">+{Math.round(Number(day.xp?.total) || 0)} XP</p>
        {day.rest_day ? (
          <p className="mt-1 break-words text-[9px] font-bold leading-snug text-[#5866f2]">День отдыха — стрик сохранён</p>
        ) : day.qualifying ? (
          <p className="mt-1 break-words text-[9px] font-bold leading-snug text-[#166534]">Квалифицирующий день</p>
        ) : null}
        {isToday && canUseRestDay && activities.length === 0 && onUseRestDay && (
          <button
            type="button"
            onClick={onUseRestDay}
            disabled={restDayBusy || isFuture}
            className="mt-2 w-full border-2 border-black bg-[#c7d2fe] px-2 py-2 text-[10px] font-black uppercase leading-snug text-[#111] hover:bg-[#ffd500] disabled:cursor-wait disabled:opacity-50"
          >
            {restDayBusy ? "Сохраняем…" : "Использовать день отдыха"}
          </button>
        )}
      </div>
    </article>
  );
}

export default function WeekCalendar({
  weekLoading,
  weekData,
  weekOptions,
  selectedWeekStart,
  onWeekChange,
  onOpenSources,
  initialActivityId = null,
  userName,
  restDayState,
  restDayBusy = false,
  restDayMessage = "",
  restDayError = "",
  onUseRestDay,
}: Props) {
  const [selectedActivity, setSelectedActivity] = useState<DayActivity | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const autoOpenedActivityId = useRef<number | null>(null);
  const reduceMotion = useReducedMotion();

  const activeWeek = selectedWeekStart || weekData?.week_start || "";
  const activeIndex = weekOptions.findIndex((week) => week.week_start === activeWeek);
  const canGoPrevious = activeIndex >= 0 && activeIndex < weekOptions.length - 1;
  const canGoNext = activeIndex > 0;
  const moveWeek = (direction: "previous" | "next") => {
    const target = weekOptions[activeIndex + (direction === "previous" ? 1 : -1)];
    if (target) onWeekChange(target.week_start);
  };

  const ledgerDays = useMemo(() => {
    const start = activeWeek;
    if (!start || (selectedWeekStart && weekData?.week_start !== selectedWeekStart)) return [];
    const fromApi: DayLedger[] = Array.isArray(weekData?.days) ? weekData.days : [];
    const dates = getCalendarWeekDates(start);
    if (dates.length !== 7) return [];
    return dates.map((date) => fromApi.find((day) => day.date === date) ?? {
      date,
      wellness: {},
      activities: [],
      xp: { effort: 0, bonuses: [], total: 0 },
      qualifying: false,
      rest_day: false,
    });
  }, [activeWeek, selectedWeekStart, weekData]);

  useEffect(() => {
    if (!initialActivityId || weekLoading || !weekData) return;
    if (selectedWeekStart && weekData.week_start !== selectedWeekStart) return;
    if (autoOpenedActivityId.current === initialActivityId) return;
    const target = ledgerDays
      .flatMap((day) => day.activities ?? [])
      .find((activity) => Number(activity.id) === initialActivityId);
    if (!target) return;
    autoOpenedActivityId.current = initialActivityId;
    setSelectedActivity(target);
  }, [initialActivityId, weekLoading, weekData, selectedWeekStart, ledgerDays]);

  const today = restDayState?.today ?? toIsoDate(new Date());
  const hasActivities = ledgerDays.some((day) => (day.activities?.length ?? 0) > 0);
  const weekBonuses: WeekBonus[] = Array.isArray(weekData?.week_bonuses) ? weekData.week_bonuses : [];

  const openActivity = (activity: DayActivity, trigger: HTMLButtonElement) => {
    triggerRef.current = trigger;
    setSelectedActivity(activity);
  };
  const closeActivity = () => {
    setSelectedActivity(null);
    window.requestAnimationFrame(() => triggerRef.current?.focus());
  };

  return (
    <section className="min-w-0 border-2 border-black border-b-0 bg-white" aria-labelledby="week-calendar-heading">
      <header className="flex min-w-0 flex-wrap items-center justify-between gap-3 border-b-2 border-black bg-[#f4f4f0] p-4 md:p-6">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Тренировки</p>
          <h2 id="week-calendar-heading" className="font-display text-2xl uppercase">Календарь недели</h2>
          <p className="mt-1 text-xs text-[#666]">{formatWeekRange(activeWeek)}</p>
          <div className="mt-2"><TrainingGlossary /></div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {weekData?.is_deload && (
              <span className={`px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-white ${weekData.deload_source === "manual" ? "bg-[#a855f7]" : "bg-[#0ea5e9]"}`}>
                Deload · {weekData.deload_source === "manual" ? "вручную" : "авто"}
              </span>
            )}
            {weekData?.paused && <span className="bg-[#666] px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-white">Пауза</span>}
          </div>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            aria-label="Предыдущая неделя тренировок"
            disabled={!canGoPrevious}
            onClick={() => moveWeek("previous")}
            className="flex h-10 w-10 shrink-0 items-center justify-center border-2 border-black bg-white font-bold transition-colors hover:bg-[#ffd500] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2] motion-reduce:transition-none disabled:opacity-30"
          >
            <ChevronLeft aria-hidden="true" size={18} />
          </button>
          <label className="sr-only" htmlFor="calendar-week-select">Выбрать неделю календаря</label>
          <select
            id="calendar-week-select"
            aria-label="Выбрать неделю календаря"
            value={activeWeek}
            onChange={(event) => onWeekChange(event.target.value)}
            className="min-w-0 max-w-[270px] border-2 border-black bg-white px-3 py-2 text-sm font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2]"
          >
            {weekOptions.length === 0 && <option value="">Нет недель</option>}
            {weekOptions.map((week) => (
              <option key={week.week_start} value={week.week_start}>{formatWeekRange(week.week_start)}</option>
            ))}
          </select>
          <button
            type="button"
            aria-label="Следующая неделя тренировок"
            disabled={!canGoNext}
            onClick={() => moveWeek("next")}
            className="flex h-10 w-10 shrink-0 items-center justify-center border-2 border-black bg-white font-bold transition-colors hover:bg-[#ffd500] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2] motion-reduce:transition-none disabled:opacity-30"
          >
            <ChevronRight aria-hidden="true" size={18} />
          </button>
        </div>
      </header>

      {restDayMessage && weekData?.is_current_week && (
        <p role="status" className="border-b border-black/10 bg-[#e9f8ee] px-4 py-2 text-sm font-bold text-[#166534]">{restDayMessage}</p>
      )}
      {restDayError && (
        <p role="alert" className="border-b border-black/10 bg-[#fff1ee] px-4 py-2 text-sm font-bold text-[#b91c1c]">{restDayError}</p>
      )}
      {restDayState?.used_this_week && weekData?.is_current_week && (
        <p className="border-b border-black/10 px-4 py-2 text-xs text-[#666]">День отдыха на этой неделе уже использован. Его можно применить только один раз и только в день без тренировок.</p>
      )}
      {weekLoading ? (
        <div className="p-4 text-sm text-[#666]" role="status">Загружаем календарь недели…</div>
      ) : ledgerDays.length === 0 ? (
        <div className="p-4 md:p-6">
          <EmptyState>Не удалось получить семь дней выбранной недели. Попробуй выбрать неделю ещё раз.</EmptyState>
          <button type="button" onClick={() => onWeekChange(activeWeek)} className="mt-3 text-sm font-bold text-[#5866f2] underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2]">
            Обновить календарь →
          </button>
        </div>
      ) : (
        <>
          {!hasActivities && (
            <div className="border-b-2 border-black p-4 md:p-6">
              <EmptyState>За выбранную неделю тренировок нет. Подключи источник или синхронизируй данные.</EmptyState>
              <button
                type="button"
                onClick={onOpenSources}
                className="mt-3 text-sm font-bold text-[#5866f2] underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2]"
              >
                Источники →
              </button>
            </div>
          )}
          <div className="grid min-w-0 grid-cols-1 gap-3 p-3 lg:grid-cols-7 lg:gap-2 lg:p-2">
            {ledgerDays.map((day) => (
              <DayColumn
                key={day.date}
                day={day}
                isToday={day.date === today}
                isFuture={day.date > today}
                onOpenActivity={openActivity}
                userName={userName}
                canUseRestDay={Boolean(restDayState?.available && day.date === restDayState.today)}
                restDayBusy={restDayBusy}
                onUseRestDay={onUseRestDay}
              />
            ))}
          </div>
        </>
      )}

      <section aria-labelledby="week-bonuses-heading" className="border-t-2 border-black">
        <div className="flex flex-wrap items-center justify-between gap-2 bg-[#ffd500] px-4 py-3">
          <h3 id="week-bonuses-heading" className="font-display text-lg uppercase">Недельные бонусы</h3>
          <span className="text-[10px] font-bold uppercase tracking-widest">{weekBonuses.length} начислений</span>
        </div>
        {weekBonuses.length === 0 ? (
          <p className="px-4 py-3 text-sm text-[#666]">Недельных бонусов нет.</p>
        ) : (
          <ul className="divide-y divide-black/10">
            {weekBonuses.map((bonus, index) => (
              <li key={`${bonus.title}-${index}`} className="flex items-start justify-between gap-3 px-4 py-3">
                <span className="min-w-0 break-words text-sm">{bonus.title}</span>
                <span className="shrink-0 font-display text-lg text-[#16a34a]">+{Math.round(Number(bonus.amount) || 0)} XP</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <AnimatePresence>
        {selectedActivity && (
          <motion.div
            className="fixed inset-0 z-[100] flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4"
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduceMotion ? 0 : 0.16 }}
            onClick={(event) => {
              if (event.target === event.currentTarget) closeActivity();
            }}
          >
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-labelledby="activity-xp-dialog-title"
              className="max-h-[92dvh] w-full max-w-2xl overflow-y-auto border-2 border-black bg-white text-[#111] shadow-[6px_6px_0_#111] sm:max-h-[88dvh]"
              data-lenis-prevent
              initial={reduceMotion ? false : { y: 12, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 8, opacity: 0 }}
              transition={{ duration: reduceMotion ? 0 : 0.16 }}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.stopPropagation();
                  closeActivity();
                }
              }}
            >
              <header className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b-2 border-black bg-[#ffd500] px-4 py-3">
                <div className="min-w-0">
                  <h2 id="activity-xp-dialog-title" className="break-words font-display text-xl uppercase">
                    {selectedActivity.name || "Тренировка"}
                  </h2>
                  <p className="mt-1 text-xs font-bold text-[#444]">
                    {selectedActivity.sport} · {formatActivityDuration(selectedActivity.moving_time_min)} · {formatDistance(selectedActivity.distance_km)} км
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeActivity}
                  aria-label="Закрыть разбор XP"
                  className="flex h-9 w-9 shrink-0 items-center justify-center border-2 border-black bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2]"
                >
                  <X aria-hidden="true" size={18} />
                </button>
              </header>
              <div className="flex justify-end px-4 pt-3">
                <ShareButton data={{
                  kind: "activity",
                  xp: Number(selectedActivity.xp) || 0,
                  title: selectedActivity.name,
                  date: selectedActivity.date,
                  sport: selectedActivity.sport,
                  durationMinutes: selectedActivity.moving_time_min,
                  distanceKm: selectedActivity.distance_km,
                  tss: selectedActivity.tss,
                  userName,
                }} />
              </div>
              <ActivityXpDetails act={selectedActivity} />
              <div className="px-4 pb-4"><ActivitySocial key={selectedActivity.id} activityId={selectedActivity.id} /></div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
