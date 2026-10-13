"use client";

import { useState, useEffect, useRef } from "react";
import type { MouseEvent, TouchEvent } from "react";
import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { getCachedUser, subscribeUser, refreshUser } from "@/lib/apiCache";
import { authApi, isAuthenticated } from "@/lib/auth";
import { Star, Sticker } from "@/components/DreamBits";
import { PauseDialog } from "@/components/Modal";
import { getApiErrorMessage, parsePauseDate, parsePauseWeeks } from "@/components/dialog-utils";
import { ErrorState, Label, SectionTitle } from "@/components/ui";
import WeekBlock from "@/components/dashboard/WeekBlock";
import EventsFeed from "@/components/dashboard/EventsFeed";
import SeasonWeeksChart from "@/components/dashboard/SeasonWeeksChart";
import QuestsBoard from "@/components/dashboard/QuestsBoard";
import RatingBoard from "@/components/dashboard/RatingBoard";
import XpDynamics from "@/components/dashboard/XpDynamics";
import WorkoutsList from "@/components/dashboard/WorkoutsList";

function useIsTouch() {
  const [touch, setTouch] = useState(false);
  useEffect(() => {
    setTouch(
      typeof window !== "undefined" &&
        (
          window.matchMedia?.("(pointer: coarse)").matches ||
          window.matchMedia?.("(hover: none)").matches ||
          "ontouchstart" in window
        )
    );
  }, []);
  return touch;
}

export default function Dashboard() {
  const [userData, setUserData] = useState<any>(null);
  const [weekData, setWeekData] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [weekOptions, setWeekOptions] = useState<{ week_start: string; label: string }[]>([]);
  const [selectedWeekStart, setSelectedWeekStart] = useState("");
  const [weekActivities, setWeekActivities] = useState<any[]>([]);
  const [weekLoading, setWeekLoading] = useState(true);
  const [seasonWeeks, setSeasonWeeks] = useState<any[]>([]);
  const [globalYourRank, setGlobalYourRank] = useState<number | null>(null);
  const [friendsYourRank, setFriendsYourRank] = useState<number | null>(null);
  const [quests, setQuests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [leaderboardTab, setLeaderboardTab] = useState<"global" | "friends" | "weekly">("weekly");
  const [weeklyBoard, setWeeklyBoard] = useState<any>(null);
  const [inviteMessage, setInviteMessage] = useState("");
  const [globalBoard, setGlobalBoard] = useState<any[]>([]);
  const [friendsBoard, setFriendsBoard] = useState<any[]>([]);
  const [boardsLoaded, setBoardsLoaded] = useState(false);
  const [isAuthed, setIsAuthed] = useState(false);
  const [pauseDialogOpen, setPauseDialogOpen] = useState(false);
  const [pauseNow, setPauseNow] = useState(0);
  const [pauseBusy, setPauseBusy] = useState(false);
  const [pauseError, setPauseError] = useState("");
  const [dashboardError, setDashboardError] = useState("");
  const isTouch = useIsTouch();
  const [touchTooltipActive, setTouchTooltipActive] = useState(false);
  const [chartKey, setChartKey] = useState(0);
  const [cursorY, setCursorY] = useState<number>(0);
  const [tooltipPortal, setTooltipPortal] = useState<HTMLElement | null>(null);

  useEffect(() => {
    setTooltipPortal(document.body);
  }, []);

  const touchStartRef = useRef<{
    time: number;
    x: number;
    y: number;
  } | null>(null);

  const TOUCH_HOLD_MS = 250;

  const handleChartTouchStart = (
    _nextState: unknown,
    event: TouchEvent<SVGGraphicsElement>
  ) => {
    const touch = event.touches[0];
    if (!touch) return;
    touchStartRef.current = {
      time: Date.now(),
      x: touch.clientX,
      y: touch.clientY,
    };
    setTouchTooltipActive(false);
  };

  const handleChartTouchMove = (
    _nextState: unknown,
    event: TouchEvent<SVGGraphicsElement>
  ) => {
    if (!touchStartRef.current) return;
    const touch = event.touches[0];
    if (!touch) return;
    setCursorY(touch.clientY);
    const elapsed = Date.now() - touchStartRef.current.time;
    const dx = Math.abs(touch.clientX - touchStartRef.current.x);
    const dy = Math.abs(touch.clientY - touchStartRef.current.y);
    if (elapsed >= TOUCH_HOLD_MS && (dx > 4 || dy > 4)) {
      setTouchTooltipActive(true);
    }
  };

  const handleChartTouchEnd = () => {
    touchStartRef.current = null;
    setTouchTooltipActive(false);
  };

  const handleMouseMove = (e: MouseEvent<HTMLDivElement>) => {
    if (!isTouch) {
      setCursorY(e.clientY);
    }
  };

  useEffect(() => {
    const cached = getCachedUser();
    if (cached) {
      setUserData(cached);
      setWeekData(cached.week || null);
      setEvents(cached.recent_events || []);
      setQuests(cached.quests || []);
    }
    const unsub = subscribeUser((u) => {
      setUserData(u);
      setQuests(u?.quests || []);
    });
    refreshUser();
    setLoading(false);
    return unsub;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setWeekLoading(true);
    authApi.get("/api/weekly-summary", {
      params: selectedWeekStart ? { week_start: selectedWeekStart } : {},
      signal: controller.signal,
    }).then((response) => {
      const result = response.data;
      setWeekData(result.week || null);
      setEvents(result.events || []);
      setWeekActivities(result.activities || []);
      setWeekOptions(result.week_options || []);
      if (!selectedWeekStart && result.week?.week_start) setSelectedWeekStart(result.week.week_start);
    }).catch((error) => {
      if (error.name !== "CanceledError" && error.name !== "AbortError") {
        setWeekActivities([]);
        setDashboardError(getApiErrorMessage(error, "Не удалось загрузить данные недели."));
      }
    }).finally(() => {
      if (!controller.signal.aborted) setWeekLoading(false);
    });
    return () => controller.abort();
  }, [selectedWeekStart]);

  useEffect(() => {
    const controller = new AbortController();
    authApi.get("/api/season-weeks", { signal: controller.signal })
      .then((response) => setSeasonWeeks(response.data.weeks || []))
      .catch((error) => { if (!controller.signal.aborted) setDashboardError(getApiErrorMessage(error, "Не удалось загрузить сезонную статистику.")); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    // после перехода с длинной главной скролл/анимации могут оставить
    // графику съехавшую геометрию — Recharts кеширует offset при монтировании.
    // Возвращаем скролл и перемонтируем график, когда всё улеглось.
    window.scrollTo(0, 0);
    const t = setTimeout(() => setChartKey((k) => k + 1), 150);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    setIsAuthed(isAuthenticated());
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const g = await authApi.get("/api/leaderboard", { params: { scope: "global", limit: 10 } });
        setGlobalBoard(g.data.entries || []);
        setGlobalYourRank(typeof g.data.your_rank === "number" ? g.data.your_rank : null);
      } catch (error: unknown) {
        setDashboardError(getApiErrorMessage(error, "Не удалось загрузить общий рейтинг."));
      }
      if (isAuthenticated()) {
        try {
          const f = await authApi.get("/api/leaderboard", { params: { scope: "friends", limit: 10 } });
          setFriendsBoard(f.data.entries || []);
          setFriendsYourRank(typeof f.data.your_rank === "number" ? f.data.your_rank : null);
        } catch (error: unknown) {
          setDashboardError(getApiErrorMessage(error, "Не удалось загрузить рейтинг друзей."));
        }
      }
      // Weekly League — публичный, как global
      try {
        const w = await authApi.get("/api/leaderboard", { params: { scope: "weekly" } });
        setWeeklyBoard(w.data);
      } catch (error: unknown) {
        setDashboardError(getApiErrorMessage(error, "Не удалось загрузить недельную лигу."));
      }
      setBoardsLoaded(true);
    })();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] flex items-center justify-center">
        <p className="font-display uppercase text-2xl text-white animate-pulse">Dreaming...</p>
      </div>
    );
  }

  const isEmpty = !userData || !userData.user;
  const data = userData ?? {
    user: { name: "athlete", level: 1, total_xp: 0, xp_to_next_level: 100 },
    recent_activities: [],
  };
  const stats = data.stats ?? { day_streak: 0, week_streak: 0, week_hours: 0, week_goal_hours: 10 };

  const chartData = [...(data.recent_activities || [])]
    .slice()
    .reverse()
    .map((act: any) => ({
      date: act.date || "",
      xp: Math.round(Number(act.xp) || 0),
      name: act.name || "workout",
      sport: act.sport || "",
      distance: act.distance_km ?? 0,
      sleepMult: act.sleep_multiplier ?? 1,
      intensityMult: act.intensity_multiplier ?? 1,
      base_xp: act.base_xp ?? 0,
      intensity_category: act.intensity_category ?? "UNKNOWN",
      streakMult: act.streak_multiplier ?? 1,
      tss_estimated: act.tss_estimated ?? false,
    }));

  const xpProgress = isEmpty ? 0 : (data.user.total_xp % 100);

  const navigateWeek = (direction: "previous" | "next") => {
    const index = weekOptions.findIndex((option) => option.week_start === (selectedWeekStart || weekData?.week_start));
    const target = weekOptions[index + (direction === "previous" ? 1 : -1)];
    if (target) setSelectedWeekStart(target.week_start);
  };

  const handleInvite = async () => {
    try {
      await navigator.clipboard.writeText(window.location.origin);
      setInviteMessage("✅ Link copied — send it to your friends");
    } catch {
      setInviteMessage("Copy the link from the address bar");
    }
    setTimeout(() => setInviteMessage(""), 3000);
  };

  const handlePauseSubmit = async (weeks: number) => {
    const validWeeks = parsePauseWeeks(weeks);
    if (validWeeks === null) {
      setPauseError("Выбери целое число недель от 0 до 8.");
      return;
    }
    const endTimestamp = userData?.user?.paused_until;
    const parsedPauseEnd = parsePauseDate(typeof endTimestamp === "string" ? endTimestamp : null);
    const currentlyPaused = Boolean(parsedPauseEnd && parsedPauseEnd.getTime() > Date.now());
    if (validWeeks === 0 && !currentlyPaused) {
      setPauseError("Сейчас активной паузы нет.");
      return;
    }

    setPauseBusy(true);
    setPauseError("");
    try {
      await authApi.post("/api/pause", { weeks: validWeeks });
      await refreshUser(true);
      setWeekData((previous: any) => previous ? { ...previous, paused: validWeeks > 0 } : previous);
      setPauseDialogOpen(false);
    } catch (error: unknown) {
      setPauseError(getApiErrorMessage(error, "Не удалось обновить паузу. Проверь соединение и попробуй ещё раз."));
    } finally {
      setPauseBusy(false);
    }
  };

  const rows = leaderboardTab === "global" ? globalBoard : friendsBoard;
  const yourRank = leaderboardTab === "global" ? globalYourRank : friendsYourRank;
  const weeklyEntries = weeklyBoard?.entries || [];
  const weekOptionIndex = weekOptions.findIndex((option) => option.week_start === (selectedWeekStart || weekData?.week_start));
  const canGoPrevious = weekOptionIndex >= 0 && weekOptionIndex < weekOptions.length - 1;
  const canGoNext = weekOptionIndex > 0;

  return (
    <main className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] px-2 sm:px-4 md:px-6 pb-2 sm:pb-4 md:pb-6 text-[#111] relative overflow-hidden flex flex-col">
      {/* ✦ сонный фон */}
      <Star className="absolute w-6 h-6 text-white/80 top-[6%] left-[3%] animate-pulse" />
      <Star className="absolute w-4 h-4 text-white/70 top-[16%] right-[6%] animate-pulse" />
      <Star className="absolute w-5 h-5 text-[#ffd500] bottom-[10%] left-[8%] animate-pulse" />
      <Star className="absolute w-7 h-7 text-white/80 bottom-[5%] right-[4%] animate-pulse" />

      {/* 📰 жёсткая таблица поверх сна */}
      <div className="relative max-w-[1400px] w-full mx-auto border-2 border-t-0 border-black bg-[#f4f4f0] flex-1 flex flex-col breathe-table">

        {/* Гость / пустое состояние */}
        {(!isAuthed || isEmpty) && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="relative border-b-2 border-black bg-white p-6 md:p-10 text-center space-y-4"
          >
            <Sticker className="top-3 left-6 bg-[#ffd500] text-black rotate-[3deg]">zzz…</Sticker>
            {isAuthed ? (
              <>
                <p className="font-display uppercase text-4xl md:text-6xl">Empty.</p>
                <Label className="text-[#666]">Level 1 · 0 XP · 0 workouts</Label>
                <p className="text-sm text-[#666] max-w-md mx-auto">
                  Синхронизируй первую тренировку — и прогресс появится здесь.
                </p>
                <Link
                  href="/profile"
                  className="inline-block px-6 py-3 bg-[#ff4b26] text-white text-xs font-bold tracking-widest uppercase hover:bg-[#5866f2] transition-colors"
                >
                  Sync →
                </Link>
              </>
            ) : (
              <>
                <p className="font-display uppercase text-4xl md:text-6xl">Sleeping?</p>
                <Label className="text-[#666]">Войди, чтобы видеть свой прогресс</Label>
                <p className="text-sm text-[#666] max-w-md mx-auto">
                  Глобальный рейтинг уже открыт ниже. Войди или зарегистрируйся, чтобы видеть свои тренировки, XP и друзей.
                </p>
                <Link
                  href="/login"
                  className="inline-block px-6 py-3 bg-[#ff4b26] text-white text-xs font-bold tracking-widest uppercase hover:bg-[#5866f2] transition-colors"
                >
                  Login →
                </Link>
              </>
            )}
          </motion.div>
        )}

        {/* Заголовок + стикер, вылезающий за рамку */}
        <div className="relative grid md:grid-cols-[1fr_auto] border-b-2 border-black">
          <Sticker className="top-2 right-4 md:right-10 bg-[#f6b8d0] text-black rotate-[-4deg]">don't stop fighting 🔥</Sticker>
          <div className="p-5 md:p-8 flex flex-col gap-3 md:border-r-2 border-black">
            <Label className="text-[#666]">Season 001 · Athlete: {data.user.name}</Label>
            <h1 className="font-display uppercase leading-[0.9] text-4xl md:text-6xl lg:text-7xl">
              Progress<span className="text-[#ff4b26]">.</span>
            </h1>
          </div>
          <Link
            href="/profile"
            className="bg-[#5866f2] text-white px-5 py-4 flex items-center justify-between gap-4 text-[11px] font-bold tracking-widest uppercase hover:bg-black transition-colors"
          >
            <span>Go to<br />profile</span>
            <span>→</span>
          </Link>
        </div>

        {dashboardError && <ErrorState message={dashboardError} onRetry={() => window.location.reload()} />}

        {/* Статистика */}
        <div className="grid md:grid-cols-3 border-b-2 border-black">
          <div className="md:border-r-2 border-black">
            <SectionTitle>Level</SectionTitle>
            <div className="p-5 md:p-6">
              <p className="font-display text-5xl md:text-7xl">{data.user.level}</p>
              <div className="w-full bg-black/10 h-3 mt-4 border border-black/20">
                <div className="bg-[#ffd500] h-full transition-all" style={{ width: `${xpProgress}%` }}></div>
              </div>
              <Label className="text-[#666] mt-3">
                {isEmpty ? "100 XP to next" : `${Math.round(data.user.xp_to_next_level)} XP to next level`}
              </Label>
            </div>
          </div>

          <div className="md:border-r-2 border-black border-t-2 md:border-t-0">
            <SectionTitle tone="yellow">Streak</SectionTitle>
            <div className="p-5 md:p-6">
              <p className="font-display text-5xl md:text-7xl text-[#ff4b26]">{stats.day_streak}</p>
              <Label className="text-[#666] mt-2">Days in a row</Label>
              <div className="mt-4 pt-3 border-t border-black/20">
                <Label className="text-[#666]">{stats.week_streak} weeks streak</Label>
              </div>
            </div>
          </div>

          <div className="border-t-2 md:border-t-0 border-black">
            <SectionTitle>Week goal</SectionTitle>
            <div className="p-5 md:p-6">
              <p className="font-display text-5xl md:text-7xl">
                {stats.week_hours}<span className="text-xl md:text-2xl text-[#666]"> / {stats.week_goal_hours}h</span>
              </p>
              <div className="w-full bg-black/10 h-3 mt-4 border border-black/20">
                <div
                  className="bg-[#5866f2] h-full transition-all"
                  style={{ width: `${Math.min(100, (stats.week_hours / stats.week_goal_hours) * 100)}%` }}
                ></div>
              </div>
              <Label className="text-[#666] mt-3">
                {Math.min(100, Math.round((stats.week_hours / stats.week_goal_hours) * 100))}% complete
              </Label>
            </div>
          </div>
        </div>

        {/* ── Твоя неделя + события (v6) — ВНУТРИ основной рамки ── */}
        {isAuthed && !isEmpty && (
          <>
            <WeekBlock
              weekData={weekData}
              weekOptions={weekOptions}
              selectedWeekStart={selectedWeekStart || weekData?.week_start || ""}
              onWeekChange={setSelectedWeekStart}
              onPreviousWeek={() => navigateWeek("previous")}
              onNextWeek={() => navigateWeek("next")}
              canGoPrevious={canGoPrevious}
              canGoNext={canGoNext}
              onPauseClick={() => { setPauseNow(Date.now()); setPauseError(""); setPauseDialogOpen(true); }}
            />
            <AnimatePresence>
              {pauseDialogOpen && (
                <PauseDialog
                  onClose={() => setPauseDialogOpen(false)}
                  onSubmit={handlePauseSubmit}
                  busy={pauseBusy}
                  error={pauseError}
                  now={pauseNow}
                  pauseSetAt={userData?.user?.pause_set_at ?? null}
                  pausedUntil={userData?.user?.paused_until ?? null}
                />
              )}
            </AnimatePresence>
            <SeasonWeeksChart weeks={seasonWeeks} />
            <EventsFeed events={events} />
            <QuestsBoard quests={quests} />
          </>
        )}

        <RatingBoard
          leaderboardTab={leaderboardTab}
          setLeaderboardTab={setLeaderboardTab}
          isAuthed={isAuthed}
          boardsLoaded={boardsLoaded}
          rows={rows}
          yourRank={yourRank}
          weeklyEntries={weeklyEntries}
          weeklyBoard={weeklyBoard}
          handleInvite={handleInvite}
          inviteMessage={inviteMessage}
        />

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

        <WorkoutsList
          weekLoading={weekLoading}
          weekActivities={weekActivities}
          selectedWeekStart={selectedWeekStart}
        />

      </div>
    </main>
  );
}