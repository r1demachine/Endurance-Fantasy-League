"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent, TouchEvent } from "react";
import { authApi } from "@/lib/auth";
import { getApiErrorMessage } from "@/components/dialog-utils";
import { EmptyState, ErrorState, Label, SectionTitle, Skeleton } from "@/components/ui";
import WorkoutsList from "@/components/dashboard/WorkoutsList";
import XpDynamics from "@/components/dashboard/XpDynamics";
import SeasonWeeksChart from "@/components/dashboard/SeasonWeeksChart";

type WeekOption = { week_start: string; label: string };

type Props = {
  userData: any;
  weekLoading: boolean;
  weekActivities: any[];
  weekOptions: WeekOption[];
  weekData: any;
  selectedWeekStart: string;
  onWeekChange: (weekStart: string) => void;
};

function useIsTouch() {
  const [touch, setTouch] = useState(false);
  useEffect(() => {
    setTouch(
      typeof window !== "undefined" &&
        (window.matchMedia?.("(pointer: coarse)").matches ||
          window.matchMedia?.("(hover: none)").matches ||
          "ontouchstart" in window)
    );
  }, []);
  return touch;
}

export default function DashboardTrainingSections({
  userData,
  weekLoading,
  weekActivities,
  weekOptions,
  weekData,
  selectedWeekStart,
  onWeekChange,
}: Props) {
  const [seasonWeeks, setSeasonWeeks] = useState<any[]>([]);
  const [seasonWeeksLoading, setSeasonWeeksLoading] = useState(true);
  const [seasonWeeksError, setSeasonWeeksError] = useState("");
  const isTouch = useIsTouch();
  const [touchTooltipActive, setTouchTooltipActive] = useState(false);
  const [chartKey, setChartKey] = useState(0);
  const [cursorY, setCursorY] = useState(0);
  const [tooltipPortal, setTooltipPortal] = useState<HTMLElement | null>(null);
  const touchStartRef = useRef<{ time: number; x: number; y: number } | null>(null);
  const TOUCH_HOLD_MS = 250;

  const loadSeasonWeeks = useCallback(async () => {
    setSeasonWeeksLoading(true);
    setSeasonWeeksError("");
    try {
      const response = await authApi.get("/api/season-weeks");
      setSeasonWeeks(Array.isArray(response.data.weeks) ? response.data.weeks : []);
    } catch (error: unknown) {
      setSeasonWeeksError(getApiErrorMessage(error, "Не удалось загрузить сезонную статистику."));
    } finally {
      setSeasonWeeksLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSeasonWeeks();
  }, [loadSeasonWeeks]);

  useEffect(() => {
    const timer = window.setTimeout(() => setChartKey((key) => key + 1), 150);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    setTooltipPortal(document.body);
  }, []);

  const currentWeekIndex = weekOptions.findIndex((option) =>
    option.week_start === (selectedWeekStart || weekData?.week_start)
  );
  const canGoPrevious = currentWeekIndex >= 0 && currentWeekIndex < weekOptions.length - 1;
  const canGoNext = currentWeekIndex > 0;

  const moveWeek = (direction: "previous" | "next") => {
    const target = weekOptions[currentWeekIndex + (direction === "previous" ? 1 : -1)];
    if (target) onWeekChange(target.week_start);
  };

  const chartData = [...(userData?.recent_activities || [])].reverse().map((activity: any) => ({
    date: activity.date || "",
    xp: Math.round(Number(activity.xp) || 0),
    name: activity.name || "workout",
    sport: activity.sport || "",
    distance: activity.distance_km ?? 0,
    sleepMult: activity.sleep_multiplier ?? 1,
    intensityMult: activity.intensity_multiplier ?? 1,
    base_xp: activity.base_xp ?? 0,
    intensity_category: activity.intensity_category ?? "UNKNOWN",
    streakMult: activity.streak_multiplier ?? 1,
    tss_estimated: activity.tss_estimated ?? false,
  }));

  const handleChartTouchStart = (_nextState: unknown, event: TouchEvent<SVGGraphicsElement>) => {
    const touch = event.touches[0];
    if (!touch) return;
    touchStartRef.current = { time: Date.now(), x: touch.clientX, y: touch.clientY };
    setTouchTooltipActive(false);
  };

  const handleChartTouchMove = (_nextState: unknown, event: TouchEvent<SVGGraphicsElement>) => {
    if (!touchStartRef.current) return;
    const touch = event.touches[0];
    if (!touch) return;
    setCursorY(touch.clientY);
    const elapsed = Date.now() - touchStartRef.current.time;
    const dx = Math.abs(touch.clientX - touchStartRef.current.x);
    const dy = Math.abs(touch.clientY - touchStartRef.current.y);
    if (elapsed >= TOUCH_HOLD_MS && (dx > 4 || dy > 4)) setTouchTooltipActive(true);
  };

  const handleChartTouchEnd = () => {
    touchStartRef.current = null;
    setTouchTooltipActive(false);
  };

  const handleMouseMove = (event: MouseEvent<HTMLDivElement>) => {
    if (!isTouch) setCursorY(event.clientY);
  };

  return (
    <div className="border-b-2 border-black">
      <section className="border-b-2 border-black bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-black bg-[#f4f4f0] p-4 md:p-6">
          <div>
            <h2 className="font-display text-2xl uppercase">Список тренировок</h2>
            <Label className="mt-1 text-[#666]">Выбери неделю для списка активности</Label>
          </div>
          <div className="flex min-w-0 items-center gap-2">
            <button type="button" aria-label="Предыдущая неделя" disabled={!canGoPrevious} onClick={() => moveWeek("previous")} className="h-10 w-10 border-2 border-black bg-white font-bold disabled:opacity-30 hover:bg-[#ffd500]">←</button>
            <select aria-label="Выбрать неделю" value={selectedWeekStart || weekData?.week_start || ""} onChange={(event) => onWeekChange(event.target.value)} className="min-w-0 max-w-[270px] border-2 border-black bg-white px-3 py-2 text-sm font-bold">
              {weekOptions.length === 0 && <option value="">Нет недель</option>}
              {weekOptions.map((option) => <option key={option.week_start} value={option.week_start}>{option.label}</option>)}
            </select>
            <button type="button" aria-label="Следующая неделя" disabled={!canGoNext} onClick={() => moveWeek("next")} className="h-10 w-10 border-2 border-black bg-white font-bold disabled:opacity-30 hover:bg-[#ffd500]">→</button>
          </div>
        </div>
        <WorkoutsList
          weekLoading={weekLoading}
          weekActivities={weekActivities}
          selectedWeekStart={selectedWeekStart || weekData?.week_start || ""}
        />
      </section>

      <section className="bg-white">
        {chartData.length > 0 ? (
          <XpDynamics
            chartData={chartData}
            chartKey={chartKey}
            isTouch={isTouch}
            touchTooltipActive={touchTooltipActive}
            tooltipPortal={tooltipPortal}
            cursorY={cursorY}
            handleChartTouchStart={handleChartTouchStart}
            handleChartTouchMove={handleChartTouchMove}
            handleChartTouchEnd={handleChartTouchEnd}
            handleMouseMove={handleMouseMove}
          />
        ) : (
          <div className="border-b-2 border-black p-4 md:p-6">
            <SectionTitle>XP Dynamics</SectionTitle>
            <EmptyState className="mt-4">Для графика XP пока нет тренировок. Синхронизируй источник или загрузи файл.</EmptyState>
          </div>
        )}
        {seasonWeeksError ? (
          <div className="p-4 md:p-6"><ErrorState message={seasonWeeksError} onRetry={() => void loadSeasonWeeks()} /></div>
        ) : seasonWeeksLoading ? (
          <div className="p-4 md:p-6"><Skeleton label="Загружаем сезонный график" rows={4} /></div>
        ) : (
          <SeasonWeeksChart weeks={seasonWeeks} />
        )}
      </section>
    </div>
  );
}
