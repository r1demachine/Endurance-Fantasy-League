"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { authApi } from "@/lib/auth";
import { formatWeekRange } from "@/lib/format";
import { getApiErrorMessage } from "@/components/dialog-utils";
import { ErrorState, Skeleton } from "@/components/ui";

type CalendarWeek = {
  week_start: string;
  week_end: string;
  total_xp: number;
  actual_load: number;
  target_load: number;
  has_summary: boolean;
  paused: boolean;
  is_deload: boolean;
  is_current: boolean;
  is_future: boolean;
};

type Props = {
  selectedWeekStart: string;
  onWeekChange: (weekStart: string) => void;
};

function mondayForDate(date: Date): Date {
  const offset = (date.getDay() + 6) % 7;
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() - offset);
}

function localIso(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function mondayForYear(year: number): string {
  return localIso(mondayForDate(new Date(year, 0, 1)));
}

function weekStatus(week: CalendarWeek): string {
  if (week.is_future) return "будущая неделя";
  if (week.paused) return "пауза";
  if (week.is_deload) return "разгрузочная неделя";
  return "обычная неделя";
}

function barStyle(week: CalendarWeek, height: number): CSSProperties {
  return {
    height: `${height}%`,
    backgroundColor: week.paused ? "#9ca3af" : week.is_deload ? "#38bdf8" : "#ff4b26",
    backgroundImage: week.paused
      ? "repeating-linear-gradient(135deg, #9ca3af 0, #9ca3af 3px, #e5e7eb 3px, #e5e7eb 6px)"
      : undefined,
  };
}

export default function YearWeeksChart({ selectedWeekStart, onWeekChange }: Props) {
  const [year, setYear] = useState<number | null>(null);
  const displayYear = year ?? new Date().getFullYear();
  const [weeks, setWeeks] = useState<CalendarWeek[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadWeeks = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    try {
      const response = await authApi.get("/api/season/weeks", {
        params: year === null ? {} : { year },
        ...(signal ? { signal } : {}),
      });
      if (signal?.aborted) return;
      setWeeks(Array.isArray(response.data.weeks) ? response.data.weeks : []);
      if (year === null && Number.isInteger(response.data.year)) {
        setYear(Number(response.data.year));
      }
    } catch (requestError: unknown) {
      if (!signal?.aborted) {
        setError(getApiErrorMessage(requestError, "Не удалось загрузить недели календарного года."));
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [year]);

  useEffect(() => {
    const controller = new AbortController();
    void loadWeeks(controller.signal);
    return () => controller.abort();
  }, [loadWeeks]);

  const monthMarkers = useMemo(() => {
    return Array.from({ length: 12 }, (_, month) => {
      const markerDate = new Date(displayYear, month, 1);
      const firstMonthWeek = localIso(mondayForDate(markerDate));
      const index = weeks.findIndex((week) => week.week_start === firstMonthWeek);
      return {
        month,
        label: new Intl.DateTimeFormat("ru-RU", { month: "short" })
          .format(markerDate)
          .replace(/\.$/, ""),
        index: Math.max(0, index),
      };
    });
  }, [displayYear, weeks]);

  const selectedWeek = weeks.find((week) => week.week_start === selectedWeekStart)
    ?? (!selectedWeekStart ? weeks.find((week) => week.is_current) ?? null : null);
  const maxXp = Math.max(1, ...weeks.map((week) => Number(week.total_xp) || 0));

  const changeYear = (delta: number) => {
    const nextYear = displayYear + delta;
    setYear(nextYear);
    onWeekChange(mondayForYear(nextYear));
  };

  return (
    <section className="border-b-2 border-black bg-white" aria-labelledby="year-weeks-heading">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-black bg-[#f4f4f0] p-4 md:p-6">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Календарный год</p>
          <h2 id="year-weeks-heading" className="font-display text-2xl uppercase">Год по неделям</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label="Предыдущий год"
            onClick={() => changeYear(-1)}
            className="h-10 w-10 border-2 border-black bg-white font-bold transition-colors hover:bg-[#ffd500]"
          >←</button>
          <span className="min-w-16 text-center font-display text-xl tabular-nums" aria-live="polite">{displayYear}</span>
          <button
            type="button"
            aria-label="Следующий год"
            onClick={() => changeYear(1)}
            className="h-10 w-10 border-2 border-black bg-white font-bold transition-colors hover:bg-[#ffd500]"
          >→</button>
        </div>
      </div>

      <div className="p-4 md:p-6">
        {loading ? (
          <Skeleton label="Загружаем год по неделям" rows={4} />
        ) : error ? (
          <ErrorState message={error} onRetry={() => void loadWeeks()} />
        ) : weeks.length === 0 ? (
          <p className="py-8 text-sm text-[#666]">Нет данных за выбранный год.</p>
        ) : (
          <>
            <div data-lenis-prevent className="overflow-x-auto overscroll-x-contain px-1 pb-2 pt-2">
              <div className="min-w-[980px] lg:min-w-0">
                <div
                  className="grid h-52 items-end gap-[3px] border-b-2 border-black/20 pb-1"
                  style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }}
                  role="group"
                  aria-label={`XP по неделям ${displayYear} года. Нажмите столбец, чтобы выбрать неделю.`}
                >
                  {weeks.map((week) => {
                    const xp = Math.round(Number(week.total_xp) || 0);
                    const height = xp === 0 ? 1.5 : Math.max(3, (xp / maxXp) * 100);
                    const selected = week.week_start === selectedWeekStart;
                    const label = `${formatWeekRange(week.week_start)}, ${xp} XP, ${weekStatus(week)}`;
                    return (
                      <button
                        key={week.week_start}
                        type="button"
                        aria-label={label}
                        aria-pressed={selected}
                        aria-describedby={selected ? "selected-year-week" : undefined}
                        title={label}
                        onClick={() => onWeekChange(week.week_start)}
                        className={`relative flex h-full min-w-0 flex-col justify-end rounded-t-sm outline-none transition-opacity focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-[#171a38] focus-visible:ring-offset-2 ${week.is_future ? "opacity-30" : "opacity-100"} ${selected && week.is_current ? "ring-2 ring-[#5866f2] ring-offset-1 outline outline-2 outline-black outline-offset-2" : selected ? "ring-2 ring-[#5866f2] ring-offset-1" : week.is_current ? "ring-2 ring-black ring-offset-1" : ""}`}
                      >
                        <span className="flex min-h-0 flex-1 items-end justify-center">
                          <span className="block w-full rounded-t-[2px] border border-black/10" style={barStyle(week, height)} />
                        </span>
                        {week.is_current && <span aria-hidden="true" className="mx-auto mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-black" />}
                      </button>
                    );
                  })}
                </div>
                <div className="relative mt-2 h-5 text-[10px] font-bold uppercase tracking-wide text-[#666]">
                  {monthMarkers.map((month) => (
                    <span
                      key={month.label}
                      className={`absolute top-0 whitespace-nowrap ${month.month === 0 ? "translate-x-0" : month.month === 11 ? "-translate-x-full" : "-translate-x-1/2"}`}
                      style={{ left: `${(month.index / Math.max(weeks.length - 1, 1)) * 100}%` }}
                    >{month.label}</span>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-black/10 pt-3 text-[10px] font-bold uppercase tracking-wide text-[#666]" aria-label="Легенда графика">
              <span className="inline-flex items-center gap-2"><span className="h-3 w-3 bg-[#ff4b26]" aria-hidden="true" />Обычная неделя</span>
              <span className="inline-flex items-center gap-2"><span className="h-3 w-3 border border-black/20" style={{ backgroundImage: "repeating-linear-gradient(135deg, #9ca3af 0, #9ca3af 3px, #e5e7eb 3px, #e5e7eb 6px)" }} aria-hidden="true" />Пауза</span>
              <span className="inline-flex items-center gap-2"><span className="h-3 w-3 bg-[#38bdf8]" aria-hidden="true" />Разгрузка</span>
              <span className="inline-flex items-center gap-2"><span className="h-3 w-3 border-2 border-[#5866f2]" aria-hidden="true" />Выбрано</span>
              <span className="inline-flex items-center gap-2 opacity-40"><span className="h-3 w-3 bg-[#ff4b26]" aria-hidden="true" />Будущая неделя</span>
            </div>

            {selectedWeek && (
              <div id="selected-year-week" role="status" className="mt-4 flex flex-wrap items-center justify-between gap-3 border-2 border-black bg-[#f4f4f0] p-3">
                <div>
                  <p className="font-bold">{formatWeekRange(selectedWeek.week_start)}</p>
                  <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-[#666]">
                    {weekStatus(selectedWeek)}{selectedWeek.is_current ? " · текущая" : ""}
                  </p>
                </div>
                <p className="font-display text-2xl text-[#ff4b26]">{Math.round(Number(selectedWeek.total_xp) || 0)} XP</p>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
