"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent, TouchEvent } from "react";
import { useRouter } from "next/navigation";
import { authApi, isAuthenticated } from "@/lib/auth";
import { getCachedUser, refreshUser, subscribeUser } from "@/lib/apiCache";
import { getApiErrorMessage } from "@/components/dialog-utils";
import { EmptyState, ErrorState, Label, SectionTitle, Skeleton, Tabs } from "@/components/ui";
import WorkoutsList from "@/components/dashboard/WorkoutsList";
import XpDynamics from "@/components/dashboard/XpDynamics";
import SeasonWeeksChart from "@/components/dashboard/SeasonWeeksChart";
import ConnectSources, { type ConnectMessage } from "@/components/ConnectSources";
import ActivityUpload from "@/components/ActivityUpload";

type TrainingTab = "list" | "charts" | "sources";

const trainingTabs: { value: TrainingTab; label: string }[] = [
  { value: "list", label: "Список" },
  { value: "charts", label: "Графики" },
  { value: "sources", label: "Источники" },
];

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

export default function TrainingPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<TrainingTab>("list");
  const [userData, setUserData] = useState<any>(null);
  const [weekOptions, setWeekOptions] = useState<{ week_start: string; label: string }[]>([]);
  const [selectedWeekStart, setSelectedWeekStart] = useState("");
  const [weekData, setWeekData] = useState<any>(null);
  const [weekActivities, setWeekActivities] = useState<any[]>([]);
  const [weekLoading, setWeekLoading] = useState(true);
  const [weekError, setWeekError] = useState("");
  const [seasonWeeks, setSeasonWeeks] = useState<any[]>([]);
  const [seasonWeeksLoading, setSeasonWeeksLoading] = useState(true);
  const [seasonWeeksError, setSeasonWeeksError] = useState("");
  const [userLoading, setUserLoading] = useState(true);
  const [sourceMessage, setSourceMessage] = useState<ConnectMessage | null>(null);
  const [sourceError, setSourceError] = useState("");
  const isTouch = useIsTouch();
  const [touchTooltipActive, setTouchTooltipActive] = useState(false);
  const [chartKey, setChartKey] = useState(0);
  const [cursorY, setCursorY] = useState(0);
  const [tooltipPortal, setTooltipPortal] = useState<HTMLElement | null>(null);

  const touchStartRef = useRef<{ time: number; x: number; y: number } | null>(null);
  const TOUCH_HOLD_MS = 250;

  useEffect(() => {
    const queryTab = new URLSearchParams(window.location.search).get("tab");
    if (queryTab === "list" || queryTab === "charts" || queryTab === "sources") {
      setActiveTab(queryTab);
    }
    const cached = getCachedUser();
    if (cached) setUserData(cached);
    const unsubscribe = subscribeUser(setUserData);
    void refreshUser();
    setUserLoading(false);
    setTooltipPortal(document.body);
    return unsubscribe;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setWeekLoading(true);
    setWeekError("");
    authApi.get("/api/weekly-summary", {
      params: selectedWeekStart ? { week_start: selectedWeekStart } : {},
      signal: controller.signal,
    }).then((response) => {
      const result = response.data;
      setWeekData(result.week || null);
      setWeekActivities(Array.isArray(result.activities) ? result.activities : []);
      setWeekOptions(Array.isArray(result.week_options) ? result.week_options : []);
      if (!selectedWeekStart && result.week?.week_start) {
        setSelectedWeekStart(result.week.week_start);
      }
    }).catch((error: unknown) => {
      const name = (error as { name?: string }).name;
      if (name !== "CanceledError" && name !== "AbortError") {
        setWeekActivities([]);
        setWeekError(getApiErrorMessage(error, "Не удалось загрузить тренировки выбранной недели."));
      }
    }).finally(() => {
      if (!controller.signal.aborted) setWeekLoading(false);
    });
    return () => controller.abort();
  }, [selectedWeekStart]);

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

  const changeTab = (tab: TrainingTab) => {
    setActiveTab(tab);
    router.replace(`/training?tab=${tab}`, { scroll: false });
  };

  const moveWeek = (direction: "previous" | "next") => {
    const currentIndex = weekOptions.findIndex((option) =>
      option.week_start === (selectedWeekStart || weekData?.week_start)
    );
    const target = weekOptions[currentIndex + (direction === "previous" ? 1 : -1)];
    if (target) setSelectedWeekStart(target.week_start);
  };

  const currentWeekIndex = weekOptions.findIndex((option) =>
    option.week_start === (selectedWeekStart || weekData?.week_start)
  );
  const canGoPrevious = currentWeekIndex >= 0 && currentWeekIndex < weekOptions.length - 1;
  const canGoNext = currentWeekIndex > 0;

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
    <main className="min-h-screen bg-[#f4f4f0] px-2 pb-24 text-[#111] sm:px-4 md:px-6 md:pb-8">
      <div className="mx-auto min-h-screen max-w-[1400px] border-2 border-t-0 border-black bg-white">
        <header className="border-b-2 border-black bg-[#ffd500] px-5 py-6 md:px-8">
          <Label className="text-black/60">ENDURANCE FANTASY LEAGUE</Label>
          <h1 className="mt-2 font-display text-4xl uppercase leading-none md:text-6xl">Тренировки.</h1>
          <p className="mt-3 max-w-3xl text-sm text-black/70">Тренировки, динамика XP и источники данных — в одном месте.</p>
        </header>

        <Tabs
          ariaLabel="Раздел тренировок"
          value={activeTab}
          onChange={changeTab}
          className="flex border-b-2 border-black"
          tabClassName="flex-1 border-r-2 border-black px-3 py-4 text-[10px] font-bold uppercase tracking-widest transition-colors md:px-6 md:text-xs"
          activeClassName="bg-[#5866f2] text-white"
          inactiveClassName="hover:bg-black/5"
          items={trainingTabs}
        />

        {activeTab === "list" && (
          <section>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-black bg-[#f4f4f0] p-4 md:p-6">
              <div>
                <h2 className="font-display text-2xl uppercase">Список тренировок</h2>
                <Label className="mt-1 text-[#666]">Выбери неделю для списка активности</Label>
              </div>
              <div className="flex min-w-0 items-center gap-2">
                <button type="button" aria-label="Предыдущая неделя" disabled={!canGoPrevious} onClick={() => moveWeek("previous")} className="h-10 w-10 border-2 border-black bg-white font-bold disabled:opacity-30 hover:bg-[#ffd500]">←</button>
                <select aria-label="Выбрать неделю" value={selectedWeekStart || weekData?.week_start || ""} onChange={(event) => setSelectedWeekStart(event.target.value)} className="min-w-0 max-w-[270px] border-2 border-black bg-white px-3 py-2 text-sm font-bold">
                  {weekOptions.length === 0 && <option value="">Нет недель</option>}
                  {weekOptions.map((option) => <option key={option.week_start} value={option.week_start}>{option.label}</option>)}
                </select>
                <button type="button" aria-label="Следующая неделя" disabled={!canGoNext} onClick={() => moveWeek("next")} className="h-10 w-10 border-2 border-black bg-white font-bold disabled:opacity-30 hover:bg-[#ffd500]">→</button>
              </div>
            </div>
            {weekError ? (
              <div className="p-4 md:p-6"><ErrorState message={weekError} onRetry={() => setSelectedWeekStart((value) => value)} /></div>
            ) : (
              <WorkoutsList weekLoading={weekLoading} weekActivities={weekActivities} selectedWeekStart={selectedWeekStart || weekData?.week_start || ""} />
            )}
          </section>
        )}

        {activeTab === "charts" && (
          <div>
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
              <section className="border-b-2 border-black bg-white p-4 md:p-6">
                <SectionTitle>XP Dynamics</SectionTitle>
                <EmptyState className="mt-4">Для графика XP пока нет тренировок. Синхронизируй источник или загрузи файл.</EmptyState>
              </section>
            )}
            {seasonWeeksError ? (
              <div className="p-4 md:p-6"><ErrorState message={seasonWeeksError} onRetry={() => void loadSeasonWeeks()} /></div>
            ) : seasonWeeksLoading ? (
              <section className="p-4 md:p-6"><Skeleton label="Загружаем сезонный график" rows={4} /></section>
            ) : (
              <SeasonWeeksChart weeks={seasonWeeks} />
            )}
          </div>
        )}

        {activeTab === "sources" && (
          <div>
            {sourceMessage && (
              <p role={sourceMessage.type === "error" ? "alert" : "status"} className={`border-b-2 border-black px-4 py-3 text-sm font-bold ${sourceMessage.type === "error" ? "bg-[#ff4b26]/10 text-[#a62910]" : sourceMessage.type === "success" ? "bg-[#16803c]/10 text-[#16803c]" : "bg-[#5866f2]/10 text-[#5866f2]"}`}>
                {sourceMessage.text}
              </p>
            )}
            {sourceError && <div className="p-4"><ErrorState message={sourceError} onRetry={() => setSourceError("")} /></div>}
            {userLoading ? (
              <div className="p-4 md:p-6"><Skeleton label="Загружаем источники" rows={4} /></div>
            ) : (
              <section className="border-b-2 border-black">
                <div className="border-b-2 border-black bg-[#f4f4f0] p-4 md:p-6">
                  <h2 className="font-display text-2xl uppercase">Источники данных</h2>
                  <p className="mt-1 text-sm text-[#666]">Статус подключения, синхронизация и прогресс импорта.</p>
                </div>
                <ConnectSources
                  hasKey={userData?.user?.has_intervals_key ?? false}
                  athleteId={userData?.user?.intervals_id ?? null}
                  onMessage={setSourceMessage}
                />
                <div className="border-t-2 border-black p-4 md:p-6">
                  <h3 className="mb-3 font-display text-xl uppercase">Загрузить тренировку</h3>
                  <ActivityUpload />
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
